"""Use five user photos to generate a cinematic board; typeset their exact goals."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import tempfile
import uuid
from collections.abc import Sequence
from contextlib import ExitStack
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from openai import AsyncOpenAI, BadRequestError
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageStat

from app.services.gift_pricing import image_cost_usd

logger = logging.getLogger(__name__)


class ImageSafetyError(RuntimeError):
    """A scene could not be produced within the image provider's safety rules."""

    def __init__(self, scene_number: int, stage: str, *,
                 categories: tuple[str, ...] = (), request_id: str | None = None) -> None:
        self.scene_number = scene_number
        self.stage = stage
        self.categories = categories
        self.request_id = request_id
        super().__init__(f"Scene {scene_number} was blocked during {stage} moderation")


def moderation_stage(exc: BadRequestError) -> str | None:
    """Distinguish a refused request from unrelated API failures."""
    if exc.code != "moderation_blocked":
        return None
    body = exc.body if isinstance(exc.body, dict) else {}
    details = body.get("moderation_details") or {}
    return (details.get("moderation_stage") or "unknown") if isinstance(details, dict) else "unknown"


def moderation_context(exc: BadRequestError) -> dict:
    """Keep the public diagnostics, without exposing the customer's inputs."""
    body = exc.body if isinstance(exc.body, dict) else {}
    details = body.get("moderation_details") or {}
    categories = details.get("categories", []) if isinstance(details, dict) else []
    return {
        "categories": tuple(value for value in categories if isinstance(value, str))
        if isinstance(categories, list) else (),
        "request_id": getattr(exc, "request_id", None),
    }

SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080), "reference": (1080, 2343)}
# The supplied visual examples are approximately 590x1280.


class ReplicateVisionBoardRenderer:
    """Legacy class name, now backed by OpenAI image edits instead of Replicate."""

    def __init__(
        self,
        api_token: str | None = None,
        output_dir: Path | str = "data/generated/wallpapers",
        openai_api_key: str | None = None,
        font_regular: Path | str | None = None,
        font_bold: Path | str | None = None,
        model: str | None = None,
        quality: str | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        from app.config import get_settings

        settings = get_settings()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.font_regular = Path(font_regular) if font_regular else None
        self.font_bold = Path(font_bold) if font_bold else None
        self.api_key = openai_api_key or settings.openai_api_key.get_secret_value()
        self.model = model or settings.openai_image_model
        self.quality = quality or settings.openai_image_quality
        self.client = client
        self.total_cost_usd = Decimal(0)

    async def build_board(
        self,
        user_id: int,
        goals: list[str],
        face_image_path: str,
        inspiration_images: Sequence[str] | None = None,
        title: str | None = None,
        aspect_ratio: str = "9:16",
    ) -> Path:
        return await self.generate_wallpaper(
            user_id, goals, face_image_path, aspect_ratio, inspiration_images, title
        )

    async def generate_wallpaper(
        self,
        user_id: int,
        goals: list[str],
        face_image_path: str,
        aspect_ratio: str = "9:16",
        inspiration_images: Sequence[str] | None = None,
        title: str | None = None,
        seed: int | None = None,
    ) -> Path:
        if aspect_ratio not in SIZES:
            raise ValueError("aspect_ratio must be '9:16', '16:9' or 'reference'")
        if len(goals) != 5 or any(not isinstance(g, str) or not g.strip() for g in goals):
            raise ValueError("Pass exactly five non-empty goal phrases")
        if inspiration_images is None or len(inspiration_images) != 4:
            raise ValueError("Pass a portrait and four scene photos")
        if not self.client and self.api_key in ("", "replace_me", None):
            raise RuntimeError("Set OPENAI_API_KEY in .env to generate cinematic artwork")
        photos = [Path(face_image_path), *(Path(path) for path in inspiration_images)]
        if any(not path.is_file() for path in photos):
            raise FileNotFoundError("One of the five photos does not exist")
        goals = [re.sub(r"\s+", " ", goal).strip() for goal in goals]
        art = await self._edit_photos(photos, self._prompt(goals, aspect_ratio), aspect_ratio)
        return await asyncio.to_thread(self._finish_art, art, user_id, goals, title, aspect_ratio)

    async def generate_gift(
        self, *, user_id: int, portrait: str | Path,
        scenes: Sequence[str], captions: Sequence[str], title: str,
        aspect_ratio: str = "9:16",
    ) -> Path:
        """Create the whole gift from one photo and an AI-generated scene plan."""
        if len(scenes) != 4 or len(captions) != 4 or not title.strip():
            raise ValueError("Gift concept needs four scenes, four captions and a title")
        if aspect_ratio not in SIZES:
            raise ValueError("Unsupported gift aspect ratio")
        if not Path(portrait).is_file():
            raise FileNotFoundError("Portrait not found")
        if not self.client and self.api_key in ("", "replace_me", None):
            raise RuntimeError("Set OPENAI_API_KEY in .env")
        prompt = self._gift_prompt(scenes, aspect_ratio)
        art = await self._edit_photos([Path(portrait)], prompt, aspect_ratio)
        return await asyncio.to_thread(
            self._finish_art, art, user_id, [*captions, title], None, aspect_ratio,
        )

    async def generate_five_photo_gift(
        self, *, user_id: int, photo_paths: Sequence[str | Path],
        scenes: Sequence[str], captions: Sequence[str], title: str,
        aspect_ratio: str = "9:16",
    ) -> Path:
        """Extend each reference photo into its own scene with AI-chosen words."""
        if len(photo_paths) != 5 or len(scenes) != 4 or len(captions) != 4 or not title.strip():
            raise ValueError("Five photos, four scenes, four captions and a title required")
        if aspect_ratio not in SIZES:
            raise ValueError("Unsupported gift aspect ratio")
        photos = [Path(path) for path in photo_paths]
        if any(not photo.is_file() for photo in photos):
            raise FileNotFoundError("One of the gift photos is missing")
        if not self.client and self.api_key in ("", "replace_me", None):
            raise RuntimeError("Set OPENAI_API_KEY in .env")
        art = await self._edit_photos(photos, self._five_photo_prompt(scenes, aspect_ratio), aspect_ratio)
        return await asyncio.to_thread(
            self._finish_art, art, user_id, [*captions, title], None, aspect_ratio,
        )

    async def generate_goal_story(
        self, *, user_id: int, photo_paths: Sequence[str | Path],
        goals: Sequence[str], assignments: Sequence[int], scenes: Sequence[str],
        style: str = "dark",
    ) -> dict[str, Path]:
        """Build two photographic posters directly from the customer's real photos."""
        if len(photo_paths) not in (1, 5) or len(goals) != 5 or len(assignments) != 5 or len(scenes) != 5:
            raise ValueError("Five customer goals and five scene pairings are required")
        if style not in ("dark", "light", "color"):
            raise ValueError("Unsupported visual style")
        if any(not isinstance(index, int) or index < 0 or index >= len(photo_paths)
               for index in assignments):
            raise ValueError("Invalid photo/goal pairing")
        if len(photo_paths) == 5 and sorted(assignments) != list(range(5)):
            raise ValueError("Each customer photo must be matched once")
        paths = [Path(photo) for photo in photo_paths]
        if any(not photo.is_file() for photo in paths):
            raise FileNotFoundError("One of the customer photos is missing")
        if not self.client and self.api_key in ("", "replace_me", None):
            raise RuntimeError("Set OPENAI_API_KEY in .env")

        # Check legibility before a paid image API request starts.
        for ratio in ("9:16", "16:9"):
            self._render_goal_labels(Image.new("RGB", SIZES[ratio]), goals, ratio)
        self.total_cost_usd = Decimal(0)
        # Keep every paid stage: a failure in the wide composition must never
        # charge for the phone artwork again on the next attempt.
        draft_prompt = self._goal_composition_prompt(
            goals, scenes, assignments, "9:16", style, len(paths))
        await self._render_story_stage(
            f"editorial_v5_{style}_mobile_draft", paths, draft_prompt,
            "9:16", 6,
        )
        polished = await self._render_story_stage(
            f"editorial_v5_{style}_mobile", [*paths, self.output_dir /
                f"editorial_v5_{style}_mobile_draft.png"],
            self._polish_prompt(goals, scenes, style, "9:16"), "9:16", 6,
        )
        results = {"mobile": await asyncio.to_thread(
            self._finish_goal_story, polished, user_id, "9:16", style, goals)}
        wide = await self._render_story_stage(
            f"editorial_v5_{style}_desktop", [*paths, self.output_dir /
                f"editorial_v5_{style}_mobile.png"],
            self._goal_composition_prompt(
                goals, scenes, assignments, "16:9", style, len(paths)),
            "16:9", 7,
        )
        results["desktop"] = await asyncio.to_thread(
            self._finish_goal_story, wide, user_id, "16:9", style, goals)
        return results

    async def _render_story_stage(
        self, name: str, references: Sequence[Path], prompt: str,
        aspect_ratio: str, scene_number: int,
    ) -> Image.Image:
        art_path = self.output_dir / f"{name}.png"
        cost_path = self.output_dir / f"{name}.json"
        if art_path.is_file() and cost_path.is_file():
            checkpoint = json.loads(cost_path.read_text(encoding="utf-8"))
            cost = Decimal(checkpoint["cost_usd"])
            if not cost.is_finite() or cost < 0:
                raise ValueError("Invalid saved composition cost")
            self.total_cost_usd += cost
            return await asyncio.to_thread(self._load, art_path)

        before = self.total_cost_usd
        try:
            art = await self._edit_photos(list(references), prompt, aspect_ratio)
        except BadRequestError as exc:
            stage = moderation_stage(exc)
            if stage is None:
                raise
            if stage != "output":
                raise ImageSafetyError(scene_number, stage, **moderation_context(exc)) from exc
            logger.warning("%s was refused at output stage; retrying in a neutral style", name)
            try:
                art = await self._edit_photos(
                    list(references), prompt + " Neutral family greeting-card mood, "
                    "modest clothes and non-intimate poses.", aspect_ratio,
                )
            except BadRequestError as retry_exc:
                retry_stage = moderation_stage(retry_exc)
                if retry_stage is None:
                    raise
                raise ImageSafetyError(scene_number, retry_stage,
                                       **moderation_context(retry_exc)) from retry_exc
        await asyncio.to_thread(self._atomic_save, art, art_path, dpi=144)
        temporary = cost_path.with_name(f".{cost_path.stem}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps({"cost_usd": str(self.total_cost_usd - before)}), encoding="utf-8")
            os.replace(temporary, cost_path)
        finally:
            temporary.unlink(missing_ok=True)
        return art

    @staticmethod
    def _goal_composition_prompt(
        goals: Sequence[str], scenes: Sequence[str], assignments: Sequence[int],
        aspect_ratio: str, style: str, photo_count: int, *, family_friendly: bool = False,
    ) -> str:
        # The positions control visual balance, not panel borders.
        placements = (
            ("upper left", "upper right", "middle left", "lower right", "bottom left")
            if aspect_ratio == "9:16" else
            ("far left upper", "left lower", "middle upper", "right lower", "far right upper")
        )
        style_notes = {
            "dark": ("low-key cinematic editorial photography, amber highlights and deep "
                     "espresso shadows, warm natural skin and atmospheric contrast"),
            "light": ("luminous editorial photography, soft daylight, ivory and sand tones, "
                      "gentle shadows and realistic skin without washed-out details"),
            "color": ("vivid real-world travel and lifestyle photography, lively varied colors, "
                      "natural skin tones and one harmonious professional color grade"),
        }
        wishes = "\n".join(
            f"Story moment {number} near {position}: {json.dumps(goal, ensure_ascii=False)}; "
            f"source photo {index + 1}; scene direction: {direction}."
            for number, (goal, index, direction, position) in enumerate(
                zip(goals, assignments, scenes, placements, strict=True), 1)
        )
        return (
            "Create a premium photographic editorial dreamscape about FIVE wishes, using "
            "the customer's real photos as identity and scene references. Give the five moments "
            "comparable visual weight in a staggered, asymmetric arrangement. No moment is a "
            "large center portrait. Carry landscape, sky, architecture, light and vegetation "
            "across the entire canvas, including its middle; do not place a person in the center. "
            + (f"Input photos 2 through {photo_count} are the customer's own additional references. "
               "Use each photo for the assigned wish even if its original background needs extending. "
               if photo_count == 5 else
               "There is one customer photo: preserve their distinctive features when their face "
               "is clearly visible, but show them in at most two moments. Let other wishes read "
               "through place, objects, distant people and candid actions, without cloning their face. ")
            + ("The final input is the already completed mobile artwork: use it ONLY for continuity "
               "of subject, scenes and colors. Recompose the wider scene afresh from the real photos. "
               if aspect_ratio == "16:9" else "")
            + "These are VISUAL instructions, not words to write into the picture:\n" + wishes + "\n"
            "Art direction: " + style_notes[style] + ". Compose one seamless photographic plane with "
            "a continuous light direction, believable depth and matching film grain. "
            "Let architecture, foliage, sky, reflections and mist naturally carry the viewer from "
            "one moment into the next: each transition occupies generous space and overlaps adjacent "
            "landscapes. Every scene must have recognizable photographic detail; do not merely "
            "hint at a wish with a tiny prop. Keep people and meaningful objects crisp; only soften the atmospheric "
            "background. Maintain each referenced person's actual facial features, age, hair, skin "
            "texture and proportions where visible; do not change or beautify faces. Use a restrained "
            "35–85 mm editorial-camera look, plausible perspective and realistic fabric. Vary scale "
            "and clothing naturally across the five moments. NO tiles, framed photos, rectangular "
            "patches, dividing lines, visible seams, repeated large heads, central oval portrait, "
            "cut-out people, ghosting, duplicate limbs, "
            "illustration, digital painting, cartoon, artificial brush textures or porcelain skin. "
            "Do not add labels, captions or a title anywhere: communicate the five goals through "
            "photography only. Generate NO text, letters, digits, signs, brands, charts or watermarks. "
            "All people wear ordinary daytime clothes in natural non-suggestive poses. "
            + ("Use a neutral family greeting-card mood, modest clothes and non-intimate poses. "
               if family_friendly else "")
            + ("This is a tall phone photograph, with breathing room around the top and bottom."
               if aspect_ratio == "9:16" else
               "This is a wide desktop photograph, recomposed for the horizontal canvas, with all five "
               "moments visible and breathing room at the sides.")
        )

    @staticmethod
    def _polish_prompt(goals: Sequence[str], scenes: Sequence[str],
                       style: str, aspect_ratio: str) -> str:
        story = "; ".join(f"{n}: {goal} ({scene})" for n, (goal, scene)
                          in enumerate(zip(goals, scenes, strict=True), 1))
        return (
            "The LAST input image is an unfinished photographic composition; the preceding "
            "images are the customer's ORIGINAL identity references. Produce a finished, "
            "realistic editorial photograph based on the draft. Preserve five equally visible "
            f"wishes in their existing staggered positions: {story}. "
            "Replace every hard or smoky boundary with plausible continuous scenery: a shared "
            "direction of natural light, related colors, believable perspective, and overlapping "
            "architecture, foliage, sky and reflections. Make the five places transition gradually "
            "into each other across the WHOLE canvas, without isolated islands or rectangular cuts. "
            "Keep the scene details sharp and rich, and preserve the person's actual face where "
            "shown in the original photos. Do not add or enlarge a face in the center, and never "
            "duplicate the same head as a repeated motif. Do not alter age, facial features, "
            "ethnicity or body proportions. Use a high-end photographic finish and natural skin "
            "texture. Avoid an illustrated look, painterly texture, pasted silhouettes, glowing "
            "halos, visible seams, frames, labels, logos, numbers, letters and ALL other text. "
            "Show ordinary non-suggestive daytime clothing and natural poses. "
            f"Keep the customer's {style} atmosphere. "
            + ("A vertical phone composition with five moments flowing top to bottom."
               if aspect_ratio == "9:16" else
               "A horizontal composition with five moments flowing left to right.")
        )

    def _finish_goal_story(self, art: Image.Image, user_id: int,
                           aspect_ratio: str, style: str, goals: Sequence[str]) -> Path:
        width, height = SIZES[aspect_ratio]
        base = ImageOps.fit(art, (width, height), method=Image.Resampling.LANCZOS)
        self._grade_goal_story(base, style)
        self._render_goal_labels(base, goals, aspect_ratio)
        name = "mobile" if aspect_ratio == "9:16" else "desktop"
        path = self.output_dir / f"manifestation_{user_id}_{name}.png"
        self._atomic_save(base, path, dpi=144)
        return path

    def _render_goal_labels(self, image: Image.Image, goals: Sequence[str], ratio: str) -> None:
        """Five exact customer wishes, set in the five scene regions without a central tile."""
        if len(goals) != 5:
            raise ValueError("Exactly five wishes are required for the finished artwork")
        positions = (
            ((.045, .045, .455, .17), (.545, .145, .965, .275),
             (.045, .395, .455, .535), (.545, .625, .965, .765),
             (.045, .795, .455, .935)) if ratio == "9:16" else
            ((.03, .055, .285, .255), (.19, .705, .435, .93),
             (.39, .045, .655, .255), (.57, .705, .835, .93),
             (.725, .055, .97, .255))
        )
        width, height = image.size
        for number, (goal, bounds) in enumerate(zip(goals, positions, strict=True), 1):
            x0, y0, x1, y1 = (round(bounds[0]*width), round(bounds[1]*height),
                              round(bounds[2]*width), round(bounds[3]*height))
            w, h = x1-x0, y1-y0
            # Let the italic inscription follow the photograph's light rather
            # than laying an opaque rectangle across a person's face.
            local_luma = ImageStat.Stat(image.crop((x0, y0, x1, y1)).convert("L")).mean[0]
            ink = (39, 29, 24, 255) if local_luma > 160 else (254, 243, 222, 255)
            outline = (248, 234, 204, 230) if local_luma > 160 else (21, 17, 16, 200)
            local = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(local)
            pad = max(7, round(width*.011))
            numeral_size = max(10, round(min(width, height)*.014))
            numeral = self._font(numeral_size)
            draw.text((pad, pad), f"{number:02}", font=numeral, fill=(218, 184, 129, 250))
            draw.line((pad + numeral_size*2, pad + numeral_size//2,
                       min(w-pad, pad + numeral_size*4), pad + numeral_size//2),
                      fill=(218, 184, 129, 200), width=max(1, width//600))
            text = re.sub(r"\s+", " ", goal).strip()
            top = pad + numeral_size + max(4, round(height*.003))
            for size in range(max(16, round(min(width, height)*.032)), 9, -1):
                font = self._serif_italic(size)
                lines = self._wrap(draw, text, font, w - 2*pad)
                spacing = max(2, round(size*.16))
                box = draw.multiline_textbbox((0, 0), lines, font=font, spacing=spacing)
                if box[2] <= w-2*pad and box[3]-box[1] <= h-top-pad:
                    break
            else:
                # Never discard an already paid-for image over a long phrase.
                # The full goal remains in the order and in the reveal story.
                size = 10
                font = self._serif_italic(size)
                spacing = 2
                lower, upper, best = 1, len(text), None
                while lower <= upper:
                    length = (lower + upper) // 2
                    excerpt = text[:length].rstrip() + ("…" if length < len(text) else "")
                    candidate = self._wrap(draw, excerpt, font, w - 2*pad)
                    bounds = draw.multiline_textbbox((0, 0), candidate, font=font, spacing=spacing)
                    if bounds[2] <= w-2*pad and bounds[3]-bounds[1] <= h-top-pad:
                        best = (candidate, bounds)
                        lower = length + 1
                    else:
                        upper = length - 1
                lines, box = best if best else ("…", draw.textbbox((0, 0), "…", font=font))
            # The soft halo follows glyphs only; no panel, card or scene boundary.
            shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(shadow).multiline_text(
                (pad, top-box[1]), lines, font=font, spacing=spacing,
                fill=outline, stroke_width=max(3, size//6),
                stroke_fill=outline)
            local.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(max(3, size//5))))
            draw = ImageDraw.Draw(local)
            draw.multiline_text((pad, top-box[1]), lines, font=font, spacing=spacing,
                                fill=ink, stroke_width=max(1, size//18),
                                stroke_fill=outline)
            image.paste(Image.alpha_composite(image.crop((x0, y0, x1, y1)).convert("RGBA"), local).convert("RGB"),
                        (x0, y0))

    def _serif_italic(self, size: int) -> ImageFont.FreeTypeFont:
        regular = self.font_regular
        candidates = [
            regular if regular and "italic" in regular.stem.lower() else None,
            Path(__file__).resolve().parents[1] / "miniapp" / "static" / "fonts" / "romantic-serif-italic.ttf",
            Path("C:/Windows/Fonts/georgiai.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSerif-Italic.ttf"),
        ]
        for path in candidates:
            if path and path.is_file():
                return ImageFont.truetype(str(path), size)
        return self._font(size)

    @staticmethod
    def _grade_goal_story(image: Image.Image, style: str) -> None:
        """Apply one color atmosphere to original portrait and generated scenes."""
        if style == "dark":
            graded = ImageEnhance.Color(image).enhance(.74)
            graded = Image.blend(graded, Image.new("RGB", image.size, (152, 109, 69)), .075)
            graded = ImageEnhance.Contrast(graded).enhance(1.07)
            graded = ImageEnhance.Brightness(graded).enhance(.93)
        elif style == "light":
            graded = Image.blend(image, Image.new("RGB", image.size, (248, 232, 209)), .045)
            graded = ImageEnhance.Brightness(graded).enhance(1.025)
        else:
            graded = ImageEnhance.Color(image).enhance(1.08)
            graded = ImageEnhance.Contrast(graded).enhance(1.025)
        image.paste(graded)

    async def generate_from_telegram(
        self,
        *,
        user_id: int,
        goals: Sequence[str],
        photo_paths: Sequence[str | Path],
        aspect_ratio: str = "9:16",
        title: str | None = None,
        seed: int | None = None,
    ) -> Path:
        """The Food_Porn bot uploads five files total: portrait first, four scenes.

        Keep the order in which Telegram delivered the photographs. The fifth
        goal is the central heading when the bot did not collect a separate title.
        """
        if len(photo_paths) != 5:
            raise ValueError("Upload exactly five photos: portrait first, then four scenes")
        return await self.generate_wallpaper(
            user_id=user_id,
            goals=list(goals),
            face_image_path=str(photo_paths[0]),
            inspiration_images=[str(path) for path in photo_paths[1:]],
            aspect_ratio=aspect_ratio,
            title=title,
            seed=seed,
        )

    async def generate_all_formats(
        self,
        user_id: int,
        goals: list[str],
        face_image_path: str,
        inspiration_images: Sequence[str] | None = None,
        title: str | None = None,
        seed: int | None = None,
    ) -> dict[str, Path]:
        # Render sequentially to avoid two large in-memory canvases at once.
        mobile = await self.generate_wallpaper(
            user_id, goals, face_image_path, "9:16", inspiration_images, title, seed
        )
        desktop = await self.generate_wallpaper(
            user_id, goals, face_image_path, "16:9", inspiration_images, title, seed
        )
        return {"mobile": mobile, "desktop": desktop}

    @staticmethod
    def _prompt(goals: list[str], aspect_ratio: str) -> str:
        scenes = "\n".join(f"Scene {number}: {goal}" for number, goal in enumerate(goals[:4], 1))
        return (
            "Create ONE premium cinematic fine-art manifestation poster using ALL five attached photos. "
            "The FIRST photo depicts the real customer: preserve recognizable facial identity, age, skin tone, "
            "hair and facial proportions. Show a single large, naturally integrated head-and-torso portrait "
            "in the CENTER. The next FOUR photos are visual references for four different surrounding scenes, "
            "one photo per scene, corresponding in order to the four customer goals below. "
            "Reimagine their backgrounds to support each goal, preserving meaningful details from the photos.\n"
            f"{scenes}\n"
            "Unify the five scenes with photorealistic, soft feathered transitions: NO collage grid, straight "
            "borders, visible rectangles, clumsy overlays, giant floating heads, duplicates or mismatched faces. "
            "Luxury editorial composition, warm champagne and muted gold, espresso shadows, soft film glow, "
            "rich photographic detail. Leave low-detail, softly shaded areas around the outer four scenes "
            "for short captions, and a warm low-detail area under the central portrait for a title. "
            "Generate ZERO text, letters, digits, labels, captions, watermarks, or logos; exact customer "
            "phrases will be typeset onto the final artwork separately. "
            f"Composition for a {'wide 16:9 desktop wallpaper' if aspect_ratio == '16:9' else 'tall 9:16 phone poster'}. "
            "Keep all essential details in the center-safe 85% so slight cropping will not cut off faces."
        )

    @staticmethod
    def _gift_prompt(scenes: Sequence[str], aspect_ratio: str) -> str:
        descriptions = "\n".join(f"Scene {index}: {scene}" for index, scene in enumerate(scenes, 1))
        return (
            "Edit the attached REAL PERSON portrait into one elegant, photorealistic luxury gift poster. "
            "Preserve this person's recognizable identity, facial structure, age and skin tone. "
            "Place their head-and-torso portrait naturally in the CENTER with soft golden light, "
            "and make four smaller, distinct dreamlike scenes around them, one at each corner. "
            "You choose the backgrounds using these art-direction notes:\n"
            f"{descriptions}\n"
            "Surrounding scenes may show scenery, architecture, objects, and distant anonymous "
            "silhouettes, but do not create additional close-up faces or invent a partner's identity. "
            "Blend every scene with soft photographic transitions and atmospheric depth, no "
            "straight borders, grid cells, floating heads, repeated faces, or visible cutout edges. "
            "Warm champagne-gold glow, espresso shadows, premium editorial photography, subtle "
            "film grain, tender emotional mood. Reserve four calm low-detail spaces near the "
            "corner scenes for captions and a warm low-detail area under the portrait for title. "
            "Absolutely no letters, text, numbers, graphic marks, logos or watermarks in the artwork. "
            f"Make a {'wide 16:9 desktop poster' if aspect_ratio == '16:9' else 'tall 9:16 phone poster'} "
            "with all critical faces and scenery inside a centered crop-safe area."
        )

    @staticmethod
    def _five_photo_prompt(scenes: Sequence[str], aspect_ratio: str) -> str:
        descriptions = "\n".join(f"Photo {number + 2}, surrounding scene {number + 1}: {scene}"
                                 for number, scene in enumerate(scenes))
        return (
            "Create ONE seamless photorealistic gift poster using all FIVE attached real photographs. "
            "Photo 1 is the central recognizable portrait. Place it in the middle, preserving the "
            "person's real face, age, pose and skin tone. Photos 2–5 are four distinct visual "
            "references for the upper-left, upper-right, lower-left, lower-right areas in this order. "
            "Show the recognizable subject of EACH reference photo once; extend its setting into "
            "a plausible, richly detailed cinematic background that fills the nearby space. "
            "Use the following scene directions, grounded in the corresponding input photographs:\n"
            f"{descriptions}\n"
            "Blend transitions through matching light, depth, colors and atmosphere; avoid pasted "
            "photo rectangles, borders, separate panels, generic empty gradients, floating faces, "
            "duplicate people and changes to identifiable people. Rich photographic detail, warm "
            "champagne highlights and espresso shadows; calm small areas for four captions near "
            "their scenes, plus a central area below the portrait for the title. Add no letters, "
            "logos, numbers or watermarks: exact captions will be typeset after generation. "
            f"Compose for {'wide 16:9 desktop wallpaper' if aspect_ratio == '16:9' else 'tall 9:16 phone wallpaper'} "
            "and keep faces and photo subjects inside the central crop-safe area."
        )

    @staticmethod
    def _prepare_photo(source: Path, dest: Path) -> None:
        with Image.open(source) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            image.save(dest, "JPEG", quality=88, optimize=True)

    @staticmethod
    def _load(path: str | Path) -> Image.Image:
        with Image.open(path) as raw:
            return ImageOps.exif_transpose(raw).convert("RGB").copy()

    async def _edit_photos(
        self, photos: list[Path], prompt: str, aspect_ratio: str,
    ) -> Image.Image:
        options = {
            "model": self.model,
            "image": [],
            "prompt": prompt,
            "size": ("1920x1088" if aspect_ratio == "16:9" else "1088x1920")
            if self.model.startswith("gpt-image-2.5") else
            ("1024x1024" if aspect_ratio == "scene" else
             "1536x1024" if aspect_ratio == "16:9" else "1024x1536"),
            "quality": self.quality,
        }
        if self.model.startswith("gpt-image-1"):
            options["input_fidelity"] = "high"
        client = self.client or AsyncOpenAI(api_key=self.api_key, timeout=240, max_retries=1)
        try:
            with tempfile.TemporaryDirectory(prefix="food_porn_ref_") as tmp:
                prepared = []
                for index, photo in enumerate(photos):
                    dest = Path(tmp) / f"photo_{index}.jpg"
                    await asyncio.to_thread(self._prepare_photo, photo, dest)
                    prepared.append(dest)
                with ExitStack() as stack:
                    options["image"] = [stack.enter_context(file.open("rb")) for file in prepared]
                    result = await client.images.edit(**options)
            if not result.data or not result.data[0].b64_json:
                raise RuntimeError("Image API returned no image")
            self.total_cost_usd += image_cost_usd(result.usage, self.model)
            data = base64.b64decode(result.data[0].b64_json)
            with Image.open(BytesIO(data)) as generated:
                generated.load()
                return generated.convert("RGB")
        finally:
            if self.client is None:
                await client.close()

    def _finish_art(
        self, generated: Image.Image, user_id: int, goals: list[str],
        title: str | None, aspect_ratio: str,
    ) -> Path:
        width, height = SIZES[aspect_ratio]
        image = ImageOps.fit(generated, (width, height), method=Image.Resampling.LANCZOS)
        self._type(image, goals, title, self._layout(aspect_ratio, 4))
        name = "mobile" if aspect_ratio == "9:16" else "desktop" if aspect_ratio == "16:9" else "reference"
        path = self.output_dir / f"manifestation_{user_id}_{name}.png"
        self._atomic_save(image, path, dpi=144)
        logger.info("Cinematic board saved: %s", path)
        return path

    @staticmethod
    def _layout(ratio: str, scene_count: int) -> dict:
        if ratio == "16:9":
            return {
                "title": (.34, .69, .66, .90),
                "labels": [
                    (.035, .085, .30, .25), (.70, .085, .965, .25),
                    (.035, .72, .30, .90), (.70, .72, .965, .90),
                ],
            }
        return {
            "title": (.17, .59, .83, .73),
            "labels": [
                (.035, .105, .34, .21), (.66, .105, .965, .21),
                (.035, .82, .38, .94), (.62, .82, .965, .94),
            ],
        }

    def _font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        configured = self.font_bold if bold else self.font_regular
        candidates = [
            configured,
            Path("C:/Windows/Fonts/georgiab.ttf" if bold else "C:/Windows/Fonts/georgia.ttf"),
            Path("C:/Windows/Fonts/timesbd.ttf" if bold else "C:/Windows/Fonts/times.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf"),
        ]
        for p in candidates:
            if p is not None and p.is_file():
                try:
                    return ImageFont.truetype(str(p), size)
                except OSError:
                    pass
        raise RuntimeError("Install DejaVu Serif, or pass font_regular/font_bold with Cyrillic glyphs")

    @staticmethod
    def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
        rows: list[str] = []
        row = ""
        for word in text.split():
            candidate = f"{row} {word}".strip()
            if row and draw.textlength(candidate, font=font) > max_w:
                rows.append(row)
                row = word
            else:
                row = candidate
        if row:
            rows.append(row)
        return "\n".join(rows)

    def _text_in_box(
        self, layer: Image.Image, text: str, bounds: tuple[float, float, float, float],
        *, title: bool = False, align: str = "center",
    ) -> None:
        w, h = layer.size
        x0, y0, x1, y1 = (round(bounds[0]*w), round(bounds[1]*h), round(bounds[2]*w), round(bounds[3]*h))
        box_w, box_h = x1-x0, y1-y0
        draw = ImageDraw.Draw(layer)
        max_size = round(w*(.047 if title else .030)) if h > w else round(h*(.048 if title else .027))
        min_size = 18 if title else 15
        for size in range(max_size, min_size-1, -1):
            font = self._font(size, bold=title)
            lines = self._wrap(draw, text, font, box_w-12)
            spacing = round(size*.24)
            bbox = draw.multiline_textbbox((0, 0), lines, font=font, spacing=spacing, align=align)
            tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
            if tw <= box_w-8 and th <= box_h-8:
                break
        else:
            raise ValueError(f"Text does not fit in its scene: {text!r}. Shorten the phrase.")
        x = x0+(box_w-tw)//2 if align == "center" else x0
        y = y0+(box_h-th)//2-bbox[1]
        # Dark soft halo improves readability on white clothing and bright skies.
        halo = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo)
        hd.multiline_text((x, y), lines, font=font, spacing=spacing, align=align,
                          fill=(15, 11, 9, 220), stroke_width=max(3, size//9), stroke_fill=(15, 11, 9, 185))
        layer.alpha_composite(halo.filter(ImageFilter.GaussianBlur(max(4, size//5))))
        draw = ImageDraw.Draw(layer)
        draw.multiline_text((x, y), lines, font=font, spacing=spacing, align=align,
                            fill=(251, 240, 218, 255), stroke_width=max(1, size//25), stroke_fill=(57, 38, 24, 200))

    def _type(self, image: Image.Image, goals: list[str], title: str | None, layout: dict) -> None:
        w, h = image.size
        # The bot supplies every visible word. Without an extra title, the
        # fifth user goal takes the large central position, appearing once.
        heading = title if title is not None else goals[4]
        scene_goals = goals if title is not None else goals[:4]
        tx0, ty0, tx1, ty1 = layout["title"]
        ribbon = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        rd = ImageDraw.Draw(ribbon)
        rd.ellipse((int((tx0-.15)*w), int((ty0-.07)*h), int((tx1+.15)*w), int((ty1+.06)*h)),
                   fill=(42, 27, 18, 125))
        image.paste(Image.alpha_composite(image.convert("RGBA"), ribbon.filter(
            ImageFilter.GaussianBlur(int(w*.04)))).convert("RGB"))
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        heading = re.sub(r"\s+", " ", heading).strip()
        self._text_in_box(overlay, heading, layout["title"], title=True)
        for goal, box in zip(scene_goals, layout["labels"], strict=False):
            self._text_in_box(overlay, goal, box)
        image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"))

    @staticmethod
    def _atomic_save(image: Image.Image, path: Path, *, dpi: int) -> None:
        temp = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp.png")
        try:
            image.save(temp, format="PNG", dpi=(dpi, dpi), optimize=True)
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    async def prepare_print_poster(
        self,
        user_id: int,
        source_image_path: str,
        width_mm: int = 300,
        height_mm: int = 400,
        dpi: int = 300,
        bleed_mm: int = 3,
    ) -> Path:
        return await asyncio.to_thread(
            self._print_sync, user_id, source_image_path, width_mm, height_mm, dpi, bleed_mm
        )

    def _print_sync(
        self, user_id: int, source: str, width_mm: int, height_mm: int,
        dpi: int, bleed_mm: int,
    ) -> Path:
        if min(width_mm, height_mm, dpi) <= 0 or bleed_mm < 0:
            raise ValueError("Print dimensions and DPI must be positive; bleed must be nonnegative")
        if width_mm > 1000 or height_mm > 1000 or dpi > 600:
            raise ValueError("Print size is too large for in-memory rendering")
        image = self._load(source)
        def px(mm: int) -> int:
            return round(mm/25.4*dpi)
        content_size = (px(width_mm), px(height_mm))
        bleed = px(bleed_mm)
        if content_size[0]*content_size[1] > 70_000_000:
            raise ValueError("Print image exceeds 70 megapixels")
        # Keep all user text visible if the source and paper have different ratios.
        background = ImageOps.fit(image, content_size, method=Image.Resampling.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(max(8, dpi//12)))
        foreground = ImageOps.contain(image, content_size, method=Image.Resampling.LANCZOS)
        background.paste(foreground, ((content_size[0]-foreground.width)//2,
                                      (content_size[1]-foreground.height)//2))
        if bleed:
            cw, ch = content_size
            expanded = Image.new("RGB", (cw+2*bleed, ch+2*bleed))
            expanded.paste(background, (bleed, bleed))
            # Repeat the outermost pixel row/column into the printer's bleed.
            expanded.paste(background.crop((0, 0, 1, ch)).resize((bleed, ch)), (0, bleed))
            expanded.paste(background.crop((cw-1, 0, cw, ch)).resize((bleed, ch)), (bleed+cw, bleed))
            expanded.paste(background.crop((0, 0, cw, 1)).resize((cw, bleed)), (bleed, 0))
            expanded.paste(background.crop((0, ch-1, cw, ch)).resize((cw, bleed)), (bleed, bleed+ch))
            for x, y, color in (
                (0, 0, background.getpixel((0, 0))),
                (bleed+cw, 0, background.getpixel((cw-1, 0))),
                (0, bleed+ch, background.getpixel((0, ch-1))),
                (bleed+cw, bleed+ch, background.getpixel((cw-1, ch-1))),
            ):
                expanded.paste(Image.new("RGB", (bleed, bleed), color), (x, y))
            background = expanded
        path = self.output_dir / f"poster_{user_id}_{width_mm}x{height_mm}mm_{dpi}dpi.png"
        if image.width < content_size[0] or image.height < content_size[1]:
            logger.warning("Print file is upscaled from %sx%s; DPI metadata cannot create missing detail", *image.size)
        self._atomic_save(background, path, dpi=dpi)
        return path
