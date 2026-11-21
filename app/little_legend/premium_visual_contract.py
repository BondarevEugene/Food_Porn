"""Genre-aware visual production contract for personalized Little Legend books.

Pure planning layer: no AI calls, media uploads or customer-photo persistence.
An illustration *slot* is a distinct scene moment, not a repeated reference photo.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class BookGenre(StrEnum):
    EPIC_FANTASY = "epic_fantasy"
    FAIRY_TALE = "fairy_tale"
    ADVENTURE = "adventure"
    DETECTIVE = "detective"
    SCIENCE_FICTION = "science_fiction"


class GenreDesign(BaseModel):
    genre: BookGenre
    body_font_family: str
    display_font_family: str
    paper_tone: str
    paper_texture: str
    ink_color: str
    cover_material: str
    cover_decoration: str
    page_ornaments: tuple[str, ...]
    bookmark_style: str


GENRE_DESIGNS: dict[BookGenre, GenreDesign] = {
    BookGenre.EPIC_FANTASY: GenreDesign(
        genre=BookGenre.EPIC_FANTASY,
        body_font_family="serif_cyrillic", display_font_family="ornamental_serif_cyrillic",
        paper_tone="#F4E6C8", paper_texture="aged_parchment_subtle",
        ink_color="#352719", cover_material="deep_blue_leather",
        cover_decoration="embossed_gold_foil",
        page_ornaments=("alchemy_symbols", "herbal_vignettes", "antique_initials"),
        bookmark_style="woven_ribbon_and_botanical",
    ),
    BookGenre.FAIRY_TALE: GenreDesign(
        genre=BookGenre.FAIRY_TALE,
        body_font_family="serif_cyrillic", display_font_family="soft_serif_cyrillic",
        paper_tone="#FFF6E9", paper_texture="watercolor_fiber_subtle",
        ink_color="#473B43", cover_material="cloth",
        cover_decoration="illustrated_gilding",
        page_ornaments=("watercolor_flora", "storybook_initials"),
        bookmark_style="silk_ribbon",
    ),
    BookGenre.ADVENTURE: GenreDesign(
        genre=BookGenre.ADVENTURE,
        body_font_family="serif_cyrillic", display_font_family="bold_serif_cyrillic",
        paper_tone="#F2E8D4", paper_texture="atlas_paper_subtle",
        ink_color="#342E24", cover_material="weathered_cloth",
        cover_decoration="compass_embossing",
        page_ornaments=("maps", "compass_roses"),
        bookmark_style="canvas_ribbon",
    ),
    BookGenre.DETECTIVE: GenreDesign(
        genre=BookGenre.DETECTIVE,
        body_font_family="serif_cyrillic", display_font_family="classic_serif_cyrillic",
        paper_tone="#F7F0E4", paper_texture="matte_paper_subtle",
        ink_color="#242424", cover_material="dark_cloth",
        cover_decoration="blind_embossing",
        page_ornaments=("case_file_lines", "chapter_seals"),
        bookmark_style="black_ribbon",
    ),
    BookGenre.SCIENCE_FICTION: GenreDesign(
        genre=BookGenre.SCIENCE_FICTION,
        body_font_family="sans_cyrillic", display_font_family="geometric_cyrillic",
        paper_tone="#F1F5F8", paper_texture="smooth_paper",
        ink_color="#172C3A", cover_material="matte_laminate",
        cover_decoration="metallic_foil",
        page_ornaments=("star_charts", "technical_grids"),
        bookmark_style="silver_ribbon",
    ),
}


class IllustrationSlot(BaseModel):
    chapter_index: int = Field(ge=1)
    moment_index: int = Field(ge=1, le=2)
    moment_id: str
    reference_index: int = Field(ge=0)
    source_reference_id: str
    scene_description: str = Field(min_length=1)
    costume_direction: str = Field(min_length=1)
    background_direction: str = Field(min_length=1)
    visual_style: str = "cinematic_painterly_fantasy"
    character_identity_required: bool = True
    full_head_safe_margin_required: bool = True
    reuse_generated_art: bool = False


class BookVisualPlan(BaseModel):
    genre: BookGenre
    design: GenreDesign
    cover_reference_id: str
    cover_character_identity_required: bool = True
    cover_full_head_safe_margin_required: bool = True
    illustrations: list[IllustrationSlot]

    @model_validator(mode="after")
    def validate_plan(self) -> BookVisualPlan:
        if self.design.genre != self.genre:
            raise ValueError("Genre design does not match visual plan")
        expected = [(index, moment) for index in range(1, len(self.illustrations) // 2 + 1)
                    for moment in (1, 2)]
        actual = [(item.chapter_index, item.moment_index) for item in self.illustrations]
        if not actual or actual != expected:
            raise ValueError("Exactly two ordered illustrations per chapter are required")
        if len({item.moment_id for item in self.illustrations}) != len(self.illustrations):
            raise ValueError("Every illustrated moment must have a unique ID")
        return self


def build_visual_plan(
    *, genre: BookGenre, reference_ids: list[str],
    chapter_moments: list[tuple[str, str]],
    costume_directions: list[str] | None = None,
    background_directions: list[str] | None = None,
) -> BookVisualPlan:
    """Assign supplied photos round-robin to distinct, story-specific moments.

    The photo is a private identity reference; it is not the generated scene.
    The caller must render each slot independently, approve likeness and crop,
    and block delivery when any slot is missing or rejected.
    """
    if not reference_ids or any(not item.strip() for item in reference_ids):
        raise ValueError("At least one valid identity reference is required")
    if len(set(reference_ids)) != len(reference_ids):
        raise ValueError("Identity references must be unique")
    if not chapter_moments or any(
        len(pair) != 2 or not all(part.strip() for part in pair)
        for pair in chapter_moments
    ):
        raise ValueError("Two distinct nonempty story moments per chapter are required")
    if any(pair[0].strip() == pair[1].strip() for pair in chapter_moments):
        raise ValueError("Story moments within a chapter must differ")
    count = len(chapter_moments) * 2
    if costume_directions is not None and len(costume_directions) != count:
        raise ValueError("Costume direction count must match illustration count")
    if background_directions is not None and len(background_directions) != count:
        raise ValueError("Background direction count must match illustration count")
    slots = []
    for chapter_index, moments in enumerate(chapter_moments, start=1):
        for moment_index, description in enumerate(moments, start=1):
            offset = (chapter_index - 1) * 2 + moment_index - 1
            reference_index = offset % len(reference_ids)
            slots.append(IllustrationSlot(
                chapter_index=chapter_index, moment_index=moment_index,
                moment_id=f"chapter-{chapter_index:02d}-moment-{moment_index}",
                reference_index=reference_index,
                source_reference_id=reference_ids[reference_index],
                scene_description=description.strip(),
                costume_direction=(
                    costume_directions[offset] if costume_directions is not None
                    else "Match the hero's role and the current story moment"
                ),
                background_direction=(
                    background_directions[offset] if background_directions is not None
                    else description.strip()
                ),
            ))
    return BookVisualPlan(
        genre=genre, design=GENRE_DESIGNS[genre],
        cover_reference_id=reference_ids[0], illustrations=slots,
    )
