"""Integration-level release gates and actionable Telegram navigation.

These tests use real production models and the real release orchestration
boundary, while replacing network/Neon/S3 calls with deterministic fakes.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.bot.handlers.little_legend_release_preflight import (
    next_release_action,
    release_actions,
)
from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.production_readiness import assess_production
from app.little_legend.release_orchestrator import (
    prepare_owned_release,
    send_owned_release,
)
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript
from app.little_legend.writer_queue import JobStatus


def _book():
    graph = build_graph(["Первое приключение", "Разгадка тайны"])
    manuscript = StoryManuscript(
        hero_name="Марта", parent_approved=True,
        chapters=[
            ChapterDraft(scene_id=f"scene_{n}", text="Приключение героя.", approved=True)
            for n in (1, 2)
        ],
    )
    jobs = [
        IllustrationJob(
            job_id=f"lli_scene_{n}", owner_id=17, story_id=29,
            scene_id=f"scene_{n}", expected_revision=1,
            estimated_cost_usd=0.05, status=JobStatus.COMPLETED,
            provider_dispatched_at=datetime.now(UTC),
        )
        for n in (1, 2)
    ]
    return graph, manuscript, jobs


@pytest.mark.parametrize(
    ("change", "expected_issue", "completed"),
    [
        ("none", None, 2),
        ("pending", "illustration_incomplete", 1),
        ("stale", "illustration_revision_stale", 1),
        ("unverified", "illustration_incomplete", 1),
        ("missing", "illustration_job_count_invalid", 1),
    ],
)
def test_real_production_status_does_not_overcount_art(change, expected_issue, completed):
    graph, manuscript, jobs = _book()
    if change == "pending":
        jobs[0].status = JobStatus.QUEUED
    elif change == "stale":
        manuscript.chapters[0].revision = 2
    elif change == "unverified":
        jobs[0].provider_dispatched_at = None
    elif change == "missing":
        jobs.pop(0)
    report = assess_production(
        graph=graph, manuscript=manuscript, jobs=jobs,
        editorial_approved=True,
    )
    assert report.completed_scenes == completed
    assert report.ready_for_export is (expected_issue is None)
    if expected_issue is not None:
        assert expected_issue in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    ("issues", "target"),
    [
        (["chapter_unapproved", "illustration_incomplete"], "ll_manuscript_review:29"),
        (["illustration_incomplete"], "ll_art_ready:29"),
        (["editorial_approval_missing"], "ll_editorial:29"),
        (["scenes_missing"], "ll_outline:29"),
        (["unknown_issue"], None),
    ],
)
def test_pdf_blockers_link_to_earliest_action(issues, target):
    action = next_release_action(29, issues)
    assert (action[1] if action else None) == target
    keyboard = release_actions(
        29, ready_for_export=False, delivery_status=None, next_action=action,
    )
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    if target is not None:
        assert callbacks[0] == target
    assert "ll_send:29" not in callbacks
    assert "ll_prepare:29" not in callbacks


@pytest.mark.parametrize("status", [DeliveryStatus.SENT, DeliveryStatus.UNCERTAIN, DeliveryStatus.SENDING])
def test_delivery_is_never_reoffered_after_attempt(status):
    keyboard = release_actions(
        29, ready_for_export=False, delivery_status=status,
        next_action=("wrong", "ll_send:29"),
    )
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "ll_send:29" not in callbacks
    assert "ll_prepare:29" not in callbacks


@pytest.mark.asyncio
async def test_persist_failure_prevents_manifest_and_telegram_dispatch():
    production = Mock()
    production.assemble.return_value = Mock()
    with (
        patch(
            "app.little_legend.release_orchestrator.get_release_manifest",
            new_callable=AsyncMock, return_value=None,
        ),
        patch(
            "app.little_legend.release_orchestrator.load_owned_production",
            new_callable=AsyncMock, return_value=production,
        ),
        patch(
            "app.little_legend.release_orchestrator.persist_release_pdf",
            side_effect=OSError("private store unavailable"),
        ),
        patch(
            "app.little_legend.release_orchestrator.register_release",
            new_callable=AsyncMock,
        ) as register,
    ):
        with pytest.raises(OSError, match="unavailable"):
            await prepare_owned_release(
                owner_id=17, story_id=29, art_store=Mock(), pdf_store=Mock(),
            )
    register.assert_not_awaited()


@pytest.mark.asyncio
async def test_uncertain_delivery_is_projected_without_retry():
    manifest = Mock(
        status=DeliveryStatus.READY, revision_fingerprint="a" * 64,
        pdf_sha256="b" * 64, scene_count=2,
    )
    outcome = Mock(status=DeliveryStatus.UNCERTAIN, telegram_message_id=None)
    with (
        patch(
            "app.little_legend.release_orchestrator.get_release_manifest",
            new_callable=AsyncMock, return_value=manifest,
        ),
        patch("app.little_legend.release_orchestrator.restore_release_pdf"),
        patch(
            "app.little_legend.release_orchestrator.dispatch_release_pdf",
            new_callable=AsyncMock, return_value=outcome,
        ) as dispatch,
        patch(
            "app.little_legend.release_orchestrator.mark_release_delivery",
            new_callable=AsyncMock,
        ) as mark,
    ):
        await send_owned_release(
            owner_id=17, story_id=29, pdf_store=Mock(), sender=Mock(),
        )
    dispatch.assert_awaited_once()
    mark.assert_awaited_once_with(
        owner_id=17, story_id=29, pdf_sha256="b" * 64,
        status=DeliveryStatus.UNCERTAIN, message_id=None,
    )
