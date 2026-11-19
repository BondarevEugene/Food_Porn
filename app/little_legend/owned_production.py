"""Load one owner-scoped book production snapshot from committed PostgreSQL data.

No AI calls, file writes or Telegram sends. Consumers can use the returned
snapshot to assess readiness or build a sealed release from private artwork.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.database.session import async_session_maker
from app.little_legend.illustration_queue_store import IllustrationJob, illustration_jobs
from app.little_legend.production_readiness import ProductionReadiness, assess_production
from app.little_legend.release_package import ReleasePackage, build_release_package
from app.little_legend.router import StoryDraft, stories
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript


@dataclass(frozen=True)
class OwnedProduction:
    owner_id: int
    story_id: int
    title: str
    dedication: str
    graph: StoryGraph
    manuscript: StoryManuscript
    jobs: list[IllustrationJob]
    editorial_approved: bool

    def readiness(self) -> ProductionReadiness:
        return assess_production(
            graph=self.graph, manuscript=self.manuscript, jobs=self.jobs,
            editorial_approved=self.editorial_approved,
        )

    def assemble(self, *, store) -> ReleasePackage:
        return build_release_package(
            owner_id=self.owner_id, story_id=self.story_id,
            title=self.title, dedication=self.dedication,
            graph=self.graph, manuscript=self.manuscript,
            jobs=self.jobs, store=store,
            editorial_approved=self.editorial_approved,
        )


async def load_owned_production(*, owner_id: int, story_id: int) -> OwnedProduction:
    """Read owner-scoped story and art jobs without starting external work."""
    if owner_id <= 0 or story_id <= 0:
        raise PermissionError("Story not found")
    async with async_session_maker() as session:
        raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ))).scalar_one_or_none()
        if raw is None:
            raise PermissionError("Story not found")
        rows = (await session.execute(select(illustration_jobs.c.payload).where(
            illustration_jobs.c.story_id == story_id,
            illustration_jobs.c.owner_id == owner_id,
        ))).scalars().all()
    draft = StoryDraft.model_validate_json(raw)
    if draft.graph is None or draft.manuscript is None:
        raise PermissionError("Book manuscript is not complete")
    decision = draft.editorial_decision
    approved = all((
        decision.hero_fidelity_reviewed,
        decision.age_appropriateness_reviewed,
        decision.narrative_continuity_reviewed,
        decision.parent_final_approval,
    ))
    jobs = [IllustrationJob.model_validate_json(payload) for payload in rows]
    return OwnedProduction(
        owner_id=owner_id, story_id=story_id,
        title=draft.title, dedication=draft.dedication,
        graph=draft.graph, manuscript=draft.manuscript,
        jobs=jobs, editorial_approved=approved,
    )
