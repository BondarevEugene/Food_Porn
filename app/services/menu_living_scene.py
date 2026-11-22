"""Reproducible, scene-led creative briefs for personalized food menus.

Pure planning: no AI calls, image edits, customer data persistence or Telegram IO.
The customer supplies meal, mood, photos and dishes; the art director chooses
the setting, wardrobe, camera action and coherent two-page visual narrative.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.services.menu_art_directions import choose_direction

MEAL_STYLES = {
    "breakfast": ("light", "airy sunlit spacious kitchen", "soft morning window light"),
    "lunch": ("color", "welcoming elegant daytime dining room", "natural midday light"),
    "dinner": ("dark", "grand intimate dining room", "warm candlelight and cinematic shadows"),
}
MOODS = {
    "family": ("warmth, belonging and home", "comfortable tasteful linen outfit"),
    "romantic": ("tenderness and closeness", "soft elegant outfit"),
    "sensual": ("playful grown-up flirtation, tasteful and non-explicit", "elegant daring evening outfit, non-explicit"),
    "festive": ("celebration and occasion", "refined formal evening outfit"),
    "playful": ("lighthearted affection and humor", "chic relaxed outfit"),
}
SETTINGS = {
    "breakfast": ("bright contemporary kitchen", "sunlit country kitchen", "French apartment kitchen"),
    "lunch": ("botanical conservatory dining room", "Mediterranean dining room", "modern open kitchen"),
    "dinner": ("candlelit art-deco dining room", "grand classic dining room", "velvet-toned private dining room"),
}
ACTIONS = (
    ("preparing food at the counter", "presenting a finished plate"),
    ("arranging a table setting", "inviting the viewer to the table"),
    ("pouring a drink beside the meal", "holding a finished dish naturally"),
    ("finishing the garnish", "sharing a warm smile over the table"),
)
PROPS = ("fresh flowers and ceramic cups", "linen napkins and seasonal fruit", "cutlery and glassware", "herbs and serving bowls")
PAPERS = ("warm ivory uncoated paper", "subtle textured cotton paper", "soft pearl matte paper")
TYPOGRAPHY = ("elegant serif with restrained handwritten accent", "editorial serif with airy sans-serif captions", "classic high-contrast serif with delicate calligraphy")
ORNAMENTS = ("fine botanical filigree", "minimal corner flourishes", "subtle engraved vines", "delicate art-deco rules")


def _pick(items: tuple[str, ...], key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return items[int.from_bytes(digest[:8], "big") % len(items)]


@dataclass(frozen=True)
class LivingSceneBrief:
    seed: str
    meal: str
    mood: str
    visual_theme: str
    setting: str
    lighting: str
    emotion: str
    wardrobe: str
    cover_action: str
    spread_action: str
    props: str
    paper: str
    typography: str
    ornament: str
    art_direction: str

    def scene_prompt(self, *, page: str) -> str:
        """A photography brief, never a request to generate text or a final PDF."""
        if page not in ("cover", "spread"):
            raise ValueError("page must be cover or spread")
        action = self.cover_action if page == "cover" else self.spread_action
        return (
            f"Photorealistic editorial lifestyle food photography. {self.setting}; "
            f"{self.lighting}. Mood: {self.emotion}. Outfit: {self.wardrobe}. "
            f"Person naturally {action}, interacting with real food and objects. "
            f"Props: {self.props}. Authentic candid gesture, believable anatomy, "
            "hands and facial proportions, coherent perspective and lighting. "
            "The person belongs organically in the environment, never a pasted-on "
            "portrait or a static memorial-style pose. Leave unobstructed space "
            "for separately typeset menu text. No generated lettering or logos. "
            "Preserve the consenting adult subject's recognizable identity from "
            "authorized reference images; never imply a reference photo is a "
            "license to alter or disclose it outside this order."
        )


def plan_living_scene(*, meal: str, mood: str, order_seed: str | int) -> LivingSceneBrief:
    """Same inputs give the same scene; different seeds offer curated variety."""
    if meal not in MEAL_STYLES:
        raise ValueError(f"Unsupported meal: {meal}")
    if mood not in MOODS:
        raise ValueError(f"Unsupported mood: {mood}")
    seed = str(order_seed)
    theme, base_setting, lighting = MEAL_STYLES[meal]
    emotion, wardrobe = MOODS[mood]
    key = f"living-scene:v1:{meal}:{mood}:{seed}"
    setting = _pick(SETTINGS[meal], key + ":setting")
    actions = ACTIONS[int.from_bytes(hashlib.sha256((key + ":actions").encode()).digest()[:8], "big") % len(ACTIONS)]
    direction = choose_direction(theme, key)
    return LivingSceneBrief(
        seed=seed,
        meal=meal,
        mood=mood,
        visual_theme=theme,
        setting=f"{base_setting}; {setting}",
        lighting=lighting,
        emotion=emotion,
        wardrobe=wardrobe,
        cover_action=actions[0],
        spread_action=actions[1],
        props=_pick(PROPS, key + ":props"),
        paper=_pick(PAPERS, key + ":paper"),
        typography=_pick(TYPOGRAPHY, key + ":type"),
        ornament=_pick(ORNAMENTS, key + ":ornament"),
        art_direction=direction.code,
    )
