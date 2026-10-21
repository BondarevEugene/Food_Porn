"""
==========================================================
FOOD_PORN

Module: Wallpaper Scene Studio
Layer: Creative Services

Responsibilities:
    - Archive source photos required for later scene editing
    - Generate one scene alternative with one image API request
    - Apply an approved alternative without touching other scenes
    - Render all static delivery formats from one approved composition
    - Build a 10–20 second living collage with optional narration
==========================================================
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import shutil
import struct
import subprocess
import tempfile
import uuid
import wave
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from openai import AsyncOpenAI
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from app.database.session import async_session_maker
from app.services.cost_tracker import log_ai_generation
from app.services.replicate_vision_board import ReplicateVisionBoardRenderer

if TYPE_CHECKING:
    from app.config import Settings
    from app.database.models import WallpaperOrder

logger = logging.getLogger(__name__)


EDIT_MODES = frozenset({"scene", "clothing", "background", "mood"})
STATIC_FORMATS = {
    "phone": (1080, 1920),
    "desktop": (1920, 1080),
    "story": (1080, 1920),
    "instagram": (1080, 1080),
    "a3": (3508, 4961),
    "telegram": (1280, 720),
}


def archive_source_photos(photo_paths: Sequence[str | Path], output_dir: str | Path) -> list[str]:
    """Keep normalized private references after Telegram/Mini App uploads are removed."""
    root = Path(output_dir) / "sources"
    root.mkdir(parents=True, exist_ok=True)
    archived: list[str] = []
    for index, source in enumerate(photo_paths):
        destination = root / f"source_{index + 1}.jpg"
        ReplicateVisionBoardRenderer._prepare_photo(Path(source), destination)
        archived.append(str(destination))
    return archived


def scene_bounds(count: int, index: int, ratio: str) -> tuple[float, float, float, float]:
    """Return an overlapping editorial region; these are not visible grid cells."""
    if not 5 <= count <= 9 or not 0 <= index < count:
        raise ValueError("Scene index is outside this collage")
    if ratio == "9:16":
        if count == 5:
            return (
                (0.00, 0.00, 0.60, 0.30), (0.40, 0.10, 1.00, 0.40),
                (0.00, 0.29, 0.60, 0.63), (0.40, 0.51, 1.00, 0.84),
                (0.00, 0.70, 0.60, 1.00),
            )[index]
        band = 1 / math.ceil(count / 2)
        row, side = divmod(index, 2)
        top = max(0.0, row * band - 0.04)
        bottom = min(1.0, (row + 1) * band + 0.04)
        return (0.0, top, 0.60, bottom) if side == 0 else (0.40, top, 1.0, bottom)
    if ratio == "16:9":
        if count == 5:
            return (
                (0.00, 0.00, 0.34, 0.53), (0.08, 0.47, 0.42, 1.00),
                (0.33, 0.00, 0.67, 0.56), (0.58, 0.47, 0.92, 1.00),
                (0.66, 0.00, 1.00, 0.53),
            )[index]
        column, row = index % 3, index // 3
        return (
            max(0.0, column / 3 - 0.03), max(0.0, row / 3 - 0.05),
            min(1.0, (column + 1) / 3 + 0.03), min(1.0, (row + 1) / 3 + 0.05),
        )
    raise ValueError("Unknown collage aspect ratio")


def _pixel_box(image: Image.Image, bounds: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return tuple(round(value * size) for value, size in zip(bounds, (*image.size, *image.size), strict=True))


def _load(path: str | Path) -> Image.Image:
    with Image.open(path) as raw:
        return ImageOps.exif_transpose(raw).convert("RGB").copy()


def _atomic_save(image: Image.Image, path: Path, *, dpi: int = 144) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp{path.suffix}")
    image.save(temporary, format="PNG", dpi=(dpi, dpi), optimize=True)
    os.replace(temporary, path)
    return path


def current_scene_preview(order: WallpaperOrder, scene_index: int, destination: Path) -> Path:
    source = Path(order.raw_mobile_path or order.mobile_path)
    image = _load(source)
    crop = image.crop(_pixel_box(image, scene_bounds(len(order.goals or []), scene_index, "9:16")))
    return _atomic_save(crop, destination)


class WallpaperSceneEditor:
    """Non-destructive scene alternatives based on the current approved board."""

    def __init__(self, renderer: ReplicateVisionBoardRenderer) -> None:
        self.renderer = renderer

    async def generate_variant(
        self, order: WallpaperOrder, scene_index: int, edit_mode: str, instruction: str,
    ) -> tuple[Path, Decimal]:
        goals = list(order.goals or [])
        scenes = list(order.scene_prompts or [])
        if edit_mode not in EDIT_MODES:
            raise ValueError("Unsupported scene edit mode")
        if not 0 <= scene_index < len(goals):
            raise ValueError("Scene index is outside this collage")
        if scene_index in set(order.locked_scene_indexes or []):
            raise PermissionError("Unlock this scene before creating another version")
        instruction = " ".join(instruction.split()).strip()
        if not 3 <= len(instruction) <= 500:
            raise ValueError("Describe the change in 3–500 characters")

        raw_mobile = Path(order.raw_mobile_path or order.mobile_path)
        if not raw_mobile.is_file():
            raise FileNotFoundError("Current collage source is unavailable")
        studio = raw_mobile.parent / "scene_studio"
        studio.mkdir(parents=True, exist_ok=True)
        context_path = studio / f"context_{scene_index}_{uuid.uuid4().hex}.png"
        await asyncio.to_thread(current_scene_preview, order, scene_index, context_path)

        references: list[Path] = [context_path]
        assignments = list(order.scene_assignments or [])
        sources = [Path(value) for value in (order.source_photo_paths or [])]
        if scene_index < len(assignments) and 0 <= int(assignments[scene_index]) < len(sources):
            assigned = sources[int(assignments[scene_index])]
            if assigned.is_file():
                references.insert(0, assigned)

        mode_text = {
            "scene": "replace the activity and scene direction",
            "clothing": "change only clothing while preserving body, face, pose and setting",
            "background": "change only the environment while preserving the person, face and clothing",
            "mood": "change only light, color and emotional mood while preserving identity and story",
        }[edit_mode]
        prompt = (
            "Create one seamless photorealistic editorial scene for an existing personal vision board. "
            f"The wish is {goals[scene_index]!r}. The previous direction was "
            f"{(scenes[scene_index] if scene_index < len(scenes) else goals[scene_index])!r}. "
            f"Requested edit: {mode_text}. Customer instruction: {instruction}. "
            "The first reference, when present, is the customer's real identity source; preserve the exact "
            "recognizable face, age, skin texture, hair and proportions. The final reference is the current "
            "approved scene and defines continuity of camera, color and subject. Preserve every successful "
            "identity detail that the instruction does not explicitly change. Fill the whole frame with one "
            "natural photographic scene, rich edge detail and soft atmospheric transitions for later blending. "
            f"Match the board's {order.visual_style or 'dark'} atmosphere. Ordinary non-suggestive clothing, "
            "plausible anatomy and perspective. No collage tiles, frames, text, letters, numbers, logo or watermark."
        )
        before = self.renderer.total_cost_usd
        try:
            image = await self.renderer._edit_photos(references, prompt, "scene")
        finally:
            context_path.unlink(missing_ok=True)
        cost = self.renderer.total_cost_usd - before
        destination = studio / f"scene_{scene_index}_variant_{uuid.uuid4().hex}.png"
        await asyncio.to_thread(_atomic_save, image, destination)
        return destination, cost

    async def apply_variant(
        self, order: WallpaperOrder, scene_index: int, scene_asset_path: str | Path,
        revision: str,
    ) -> dict[str, Path]:
        goals = list(order.goals or [])
        if not 0 <= scene_index < len(goals):
            raise ValueError("Scene index is outside this collage")
        asset = await asyncio.to_thread(_load, scene_asset_path)
        folder = Path(order.mobile_path).parent / "scene_studio" / "revisions"
        folder.mkdir(parents=True, exist_ok=True)
        output: dict[str, Path] = {}
        for ratio, raw_value, fallback in (
            ("9:16", order.raw_mobile_path, order.mobile_path),
            ("16:9", order.raw_desktop_path, order.desktop_path),
        ):
            raw = await asyncio.to_thread(_load, raw_value or fallback)
            blended = await asyncio.to_thread(
                self._blend_scene, raw, asset, scene_bounds(len(goals), scene_index, ratio)
            )
            name = "mobile" if ratio == "9:16" else "desktop"
            raw_path = folder / f"revision_{revision}_{name}_raw.png"
            await asyncio.to_thread(_atomic_save, blended, raw_path)
            finished = blended.copy()
            self.renderer._grade_goal_story(finished, order.visual_style or "dark")
            self.renderer._render_goal_labels(finished, goals, ratio)
            final_path = folder / f"revision_{revision}_{name}.png"
            await asyncio.to_thread(_atomic_save, finished, final_path)
            output[f"raw_{name}"] = raw_path
            output[name] = final_path
        return output

    @staticmethod
    def _blend_scene(
        canvas: Image.Image, asset: Image.Image,
        bounds: tuple[float, float, float, float],
    ) -> Image.Image:
        box = _pixel_box(canvas, bounds)
        width, height = box[2] - box[0], box[3] - box[1]
        replacement = ImageOps.fit(asset, (width, height), method=Image.Resampling.LANCZOS)
        inset = max(10, round(min(width, height) * 0.09))
        mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (inset, inset, width - inset, height - inset),
            radius=max(12, inset), fill=255,
        )
        mask = mask.filter(ImageFilter.GaussianBlur(inset))
        result = canvas.copy()
        result.paste(replacement, (box[0], box[1]), mask)
        return result


class WallpaperExportService:
    """Derive every reusable channel format locally, with no additional AI calls."""

    def __init__(self, order: WallpaperOrder) -> None:
        self.order = order
        self.root = Path(order.mobile_path).parent / "exports"
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def source_revision(self) -> str:
        digest = hashlib.sha256()
        for value in (self.order.mobile_path, self.order.desktop_path):
            path = Path(value)
            digest.update(str(path).encode())
            if path.is_file():
                stat = path.stat()
                digest.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode())
        return digest.hexdigest()[:20]

    def render_static(self) -> dict[str, tuple[Path, int, int]]:
        mobile = _load(self.order.mobile_path)
        desktop = _load(self.order.desktop_path)
        sources = {
            "phone": mobile, "story": mobile, "instagram": mobile,
            "a3": mobile, "desktop": desktop, "telegram": desktop,
        }
        rendered: dict[str, tuple[Path, int, int]] = {}
        for kind, size in STATIC_FORMATS.items():
            image = self._safe_canvas(sources[kind], size)
            destination = self.root / f"{kind}_{self.source_revision}.png"
            _atomic_save(image, destination, dpi=300 if kind == "a3" else 144)
            rendered[kind] = (destination, *size)
        return rendered

    @staticmethod
    def _safe_canvas(source: Image.Image, size: tuple[int, int]) -> Image.Image:
        background = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(max(12, min(size) // 45)))
        background = Image.blend(background, Image.new("RGB", size, "#151318"), 0.18)
        foreground = ImageOps.contain(source, size, method=Image.Resampling.LANCZOS)
        background.paste(foreground, ((size[0] - foreground.width) // 2,
                                      (size[1] - foreground.height) // 2))
        return background

    async def render_video(
        self, *, settings: Settings, goals: Sequence[str], final_phrase: str,
        duration_seconds: int = 15, voice_path: str | Path | None = None,
        music_path: str | Path | None = None, ai_voice: bool = False,
    ) -> Path:
        duration_seconds = min(20, max(10, int(duration_seconds)))
        final_phrase = " ".join(final_phrase.split()).strip()[:500]
        narration: Path | None = Path(voice_path) if voice_path else None
        if ai_voice and final_phrase:
            narration = self.root / f"narration_{self.source_revision}.mp3"
            await self._ai_voice(settings, final_phrase, narration)
        return await asyncio.to_thread(
            self._render_video_sync, list(goals), final_phrase, duration_seconds,
            narration, Path(music_path) if music_path else None,
        )

    async def _ai_voice(self, settings: Settings, text: str, destination: Path) -> None:
        key = settings.openai_api_key.get_secret_value()
        client = AsyncOpenAI(api_key=key, timeout=120, max_retries=1)
        try:
            response = await client.audio.speech.create(
                model=settings.openai_tts_model,
                voice=settings.openai_tts_voice,
                input=text,
                response_format="mp3",
            )
            payload = getattr(response, "content", None)
            if payload is None and hasattr(response, "read"):
                payload = await response.read()
            if not isinstance(payload, bytes) or not payload:
                raise RuntimeError("OpenAI speech response is empty")
            destination.write_bytes(payload)
            try:
                async with async_session_maker() as session:
                    await log_ai_generation(
                        session,
                        user_id=self.order.telegram_user_id,
                        model_name=settings.openai_tts_model,
                        prompt_tokens=0,
                        completion_tokens=0,
                        cost_usd=settings.openai_tts_fallback_cost_usd,
                        operation="wallpaper_ai_voice",
                        product_type="wallpaper",
                        order_id=self.order.id,
                        pricing_source="fallback_estimate",
                        details={"characters": len(text), "voice": settings.openai_tts_voice},
                    )
            except Exception:
                # A ledger outage must not discard an already generated narration.
                logger.exception("Could not persist AI narration cost")
        finally:
            await client.close()

    def _render_video_sync(
        self, goals: list[str], final_phrase: str, duration: int,
        narration: Path | None, music: Path | None,
    ) -> Path:
        ffmpeg = self._ffmpeg()
        fps, size = 12, (720, 1280)
        source = _load(self.order.raw_mobile_path or self.order.mobile_path)
        segments = max(1, len(goals) + (1 if final_phrase else 0))
        total_frames = duration * fps
        with tempfile.TemporaryDirectory(prefix="food_porn_video_") as temporary:
            frames = Path(temporary) / "frames"
            frames.mkdir()
            for frame_no in range(total_frames):
                position = frame_no * segments / total_frames
                segment = min(segments - 1, int(position))
                local_progress = position - int(position)
                frame = self._story_frame(
                    source, goals, final_phrase, segment, local_progress, size
                )
                # The final 18% of each shot dissolves into the following goal.
                if local_progress > 0.82 and segment + 1 < segments:
                    following = self._story_frame(
                        source, goals, final_phrase, segment + 1,
                        (local_progress - 0.82) / 0.18 * 0.12, size,
                    )
                    frame = Image.blend(frame, following, (local_progress - 0.82) / 0.18)
                frame.save(frames / f"frame_{frame_no:05d}.jpg", "JPEG", quality=88)

            silent = Path(temporary) / "silent.mp4"
            subprocess.run(
                [ffmpeg, "-y", "-loglevel", "error", "-framerate", str(fps),
                 "-i", str(frames / "frame_%05d.jpg"), "-c:v", "libx264",
                 "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                 "-movflags", "+faststart", str(silent)],
                check=True, timeout=300,
            )
            soundtrack = music if music and music.is_file() else Path(temporary) / "ambient.wav"
            if soundtrack.name == "ambient.wav":
                self._ambient_track(soundtrack, duration)
            destination = self.root / f"living_collage_{self.source_revision}.mp4"
            command = [ffmpeg, "-y", "-loglevel", "error", "-i", str(silent),
                       "-stream_loop", "-1", "-i", str(soundtrack)]
            if narration and narration.is_file():
                command += ["-i", str(narration), "-filter_complex",
                            "[1:a]volume=0.22[m];[2:a]volume=1.0[v];[m][v]amix=inputs=2:duration=first[a]",
                            "-map", "0:v", "-map", "[a]"]
            else:
                command += ["-map", "0:v", "-map", "1:a"]
            command += ["-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", str(duration),
                        "-shortest", "-movflags", "+faststart", str(destination)]
            subprocess.run(command, check=True, timeout=300)
        return destination

    @staticmethod
    def _ffmpeg() -> str:
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError as exc:
            executable = shutil.which("ffmpeg")
            if not executable:
                raise RuntimeError("FFmpeg is unavailable") from exc
            return executable

    @staticmethod
    def _ken_burns(source: Image.Image, size: tuple[int, int], progress: float, seed: int) -> Image.Image:
        base = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
        scale = 1.02 + 0.08 * progress
        enlarged = base.resize((round(size[0] * scale), round(size[1] * scale)), Image.Resampling.LANCZOS)
        travel_x = enlarged.width - size[0]
        travel_y = enlarged.height - size[1]
        x = round(travel_x * (progress if seed % 2 == 0 else 1 - progress))
        y = round(travel_y * (1 - progress if seed % 3 == 0 else progress))
        return enlarged.crop((x, y, x + size[0], y + size[1]))

    @classmethod
    def _story_frame(
        cls, source: Image.Image, goals: list[str], final_phrase: str,
        segment: int, progress: float, size: tuple[int, int],
    ) -> Image.Image:
        if segment < len(goals):
            box = _pixel_box(source, scene_bounds(len(goals), segment, "9:16"))
            still = source.crop(box)
            label = goals[segment]
        else:
            still = source
            label = final_phrase
        frame = cls._ken_burns(still, size, progress, segment)
        cls._video_caption(
            frame, label, final=segment >= len(goals), opacity=min(1.0, progress / 0.16)
        )
        return frame

    @staticmethod
    def _video_caption(
        image: Image.Image, text: str, *, final: bool, opacity: float = 1.0
    ) -> None:
        text = " ".join(text.split()).strip()
        if not text:
            return
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf", 42 if final else 34)
        except OSError:
            font = ImageFont.load_default()
        words, lines, row = text.split(), [], ""
        for word in words:
            candidate = f"{row} {word}".strip()
            if row and draw.textlength(candidate, font=font) > image.width * 0.78:
                lines.append(row)
                row = word
            else:
                row = candidate
        if row:
            lines.append(row)
        label = "\n".join(lines[:4])
        bounds = draw.multiline_textbbox((0, 0), label, font=font, spacing=8, align="center")
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        x, y = (image.width - width) // 2, image.height - height - 105
        draw.rounded_rectangle((x - 28, y - 22, x + width + 28, y + height + 22), 24, fill=(15, 12, 18, 150))
        draw.multiline_text((x, y), label, font=font, fill=(255, 244, 224, 255), spacing=8, align="center")
        if opacity < 1:
            overlay.putalpha(overlay.getchannel("A").point(lambda alpha: round(alpha * opacity)))
        image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"))

    @staticmethod
    def _ambient_track(destination: Path, duration: int) -> None:
        sample_rate = 22_050
        with wave.open(str(destination), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            for sample in range(sample_rate * duration):
                second = sample / sample_rate
                fade = min(1.0, second / 2, (duration - second) / 2)
                value = sum(math.sin(2 * math.pi * frequency * second) * volume
                            for frequency, volume in ((174.61, 0.22), (220.0, 0.16), (261.63, 0.10)))
                output.writeframesraw(struct.pack("<h", round(32767 * value * max(0, fade))))
