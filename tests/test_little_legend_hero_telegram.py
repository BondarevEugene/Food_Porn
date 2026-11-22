"""Hero approval is a separate persisted stage, not automatic photo consent."""
from pathlib import Path

from app.little_legend.blueprint import quick_blueprint

SOURCE = Path("app/bot/handlers/little_legend.py").read_text(encoding="utf-8")


def test_hero_approval_is_explicit():
    blueprint = quick_blueprint("Мария")
    assert not blueprint.family_approved
    assert not blueprint.characters[0].photo_consent_confirmed
    assert 'callback_data=f"ll_hero_approve:{story_id}"' in SOURCE
    assert '("Профиль героя", hero_done, f"ll_hero_review:{story_id}")' in SOURCE


def test_hero_approval_is_owner_scoped_and_persisted():
    assert "async def little_legend_hero_approve" in SOURCE
    section = SOURCE.split("async def little_legend_hero_approve", 1)[1].split(
        '@router.callback_query(F.data.startswith("ll_book_tools:"))', 1,
    )[0]
    assert "stories.c.owner_id == callback.from_user.id" in section
    assert "with_for_update()" in section
    assert "blueprint.family_approved = True" in section
    assert "await session.commit()" in section
    assert "photo_consent_confirmed = True" not in section
