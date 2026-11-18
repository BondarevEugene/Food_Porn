"""Objective diagnostics must not imply automatic literary approval."""
from app.little_legend.editorial_diagnostics import diagnose_manuscript
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def test_short_chapter_is_flagged_and_never_auto_approved():
    manuscript = StoryManuscript(
        hero_name="Марта",
        chapters=[ChapterDraft(scene_id="one", text="Марта нашла ключ.")],
    )
    report = diagnose_manuscript(manuscript)
    assert report.total_words == 3
    assert any(f.code == "chapter_too_short" for f in report.findings)
    assert report.human_review_required
    assert not report.literary_quality_verified


def test_cross_chapter_repetition_is_flagged_without_exposing_prose():
    sentence = "Марта открыла дверь и увидела старую башню."
    manuscript = StoryManuscript(
        hero_name="Марта",
        chapters=[
            ChapterDraft(scene_id="one", text=sentence),
            ChapterDraft(scene_id="two", text=sentence),
        ],
    )
    report = diagnose_manuscript(manuscript, minimum_words=1)
    assert any(f.code == "cross_chapter_repetition" for f in report.findings)
    assert sentence not in report.model_dump_json()


def test_repeated_sentence_in_one_chapter_is_flagged():
    sentence = "Марта открыла дверь и увидела старую башню."
    manuscript = StoryManuscript(
        hero_name="Марта",
        chapters=[ChapterDraft(scene_id="one", text=" ".join([sentence] * 3))],
    )
    report = diagnose_manuscript(manuscript, minimum_words=1)
    assert any(f.code == "repeated_sentence" for f in report.findings)
