"""Owner-scoped Little Legend production checkpoint for Telegram."""
from __future__ import annotations

from collections import Counter

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.database.session import async_session_maker
from app.little_legend.illustration_queue_store import illustration_jobs
from app.little_legend.production_readiness import assess_production
from app.little_legend.router import StoryDraft, stories
from app.little_legend.story_writer import StoryManuscript
from app.little_legend.writer_queue_store import writer_jobs

router = Router(name="little_legend_checkpoint")


def checkpoint_summary(
    draft: StoryDraft, writer_statuses: list[str], illustration_payloads: list[str],
) -> str:
    """Summarize persisted work; never equate completed jobs with approved book."""
    graph = draft.graph
    manuscript = draft.manuscript or StoryManuscript(hero_name=draft.hero)
    expected = {node.id for node in graph.nodes} if graph else set()
    chapters = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    completed = sum(scene_id in chapters for scene_id in expected)
    approved = sum(
        scene_id in chapters and chapters[scene_id].approved
        for scene_id in expected
    )
    statuses = Counter(writer_statuses)
    lines = [
        "📚 Производство Little Legend",
        f"Главы сохранены: {completed}/{len(expected)}",
        f"Главы утверждены: {approved}/{len(expected)}",
        "Рукопись утверждена родителем: "
        + ("да" if manuscript.parent_approved else "нет"),
    ]
    if statuses:
        lines.append(
            "Очередь писателя: " + ", ".join(
                f"{key}: {value}" for key, value in sorted(statuses.items())
            )
        )
    if graph is None:
        lines.append("⏳ Сначала необходимо создать сюжетный план.")
        return "\n".join(lines)
    from app.little_legend.illustration_queue_store import IllustrationJob

    jobs = [IllustrationJob.model_validate_json(raw) for raw in illustration_payloads]
    decision = draft.editorial_decision
    editorial_approved = all((
        decision.hero_fidelity_reviewed,
        decision.age_appropriateness_reviewed,
        decision.narrative_continuity_reviewed,
        decision.parent_final_approval,
    ))
    report = assess_production(
        graph=graph, manuscript=manuscript, jobs=jobs,
        editorial_approved=editorial_approved,
    )
    by_stage = Counter(issue.stage.value for issue in report.issues)
    lines.append(
        "Иллюстрации и выпуск: "
        + ("готово к сборке" if report.ready_for_export else "требуют доработки")
    )
    if by_stage:
        lines.append(
            "Незакрытые этапы: " + ", ".join(
                f"{key}: {count}" for key, count in sorted(by_stage.items())
            )
        )
    lines.append("PDF и отправка проверяются отдельно.")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("ll_checkpoint:"))
async def show_checkpoint(callback: CallbackQuery) -> None:
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Доступно только в личном чате", show_alert=True)
        return
    try:
        story_id = int((callback.data or "").split(":", 1)[1])
        if story_id <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await callback.answer("Неверная книга", show_alert=True)
        return
    owner_id = callback.from_user.id
    async with async_session_maker() as session:
        raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ))).scalar_one_or_none()
        if raw is None:
            await callback.answer("Книга не найдена", show_alert=True)
            return
        writer_statuses = (await session.execute(select(writer_jobs.c.status).where(
            writer_jobs.c.story_id == story_id,
            writer_jobs.c.owner_id == owner_id,
        ))).scalars().all()
        illustrations = (await session.execute(select(illustration_jobs.c.payload).where(
            illustration_jobs.c.story_id == story_id,
            illustration_jobs.c.owner_id == owner_id,
        ))).scalars().all()
    await callback.message.answer(
        checkpoint_summary(
            StoryDraft.model_validate_json(raw),
            list(writer_statuses), list(illustrations),
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="⬅️ К книге", callback_data=f"ll_book:{story_id}",
            ),
        ]]),
    )
    await callback.answer()
