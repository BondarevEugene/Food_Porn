"""Owner-scoped recovery dashboard for Little Legend production."""
from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from app.little_legend.production_checkpoint_store import (
    list_unfinished_checkpoints,
)
from app.little_legend.production_recovery import (
    RecoveryAction,
    RecoveryPlan,
    plan_owned_recovery,
)


class RecoveryDashboard(BaseModel):
    owner_id: int = Field(gt=0)
    total_unfinished: int = Field(ge=0)
    blocked: int = Field(ge=0)
    actionable: int = Field(ge=0)
    action_counts: dict[str, int] = Field(default_factory=dict)
    plans: list[RecoveryPlan] = Field(default_factory=list)


def summarize_recovery(
    *, owner_id: int, plans: list[RecoveryPlan],
) -> RecoveryDashboard:
    """Aggregate operational metrics without exposing children's content."""
    if any(plan.owner_id != owner_id for plan in plans):
        raise PermissionError("Recovery plan belongs to another owner")
    if len({plan.story_id for plan in plans}) != len(plans):
        raise ValueError("Duplicate stories in recovery dashboard")
    counts: Counter[str] = Counter(
        action.value for plan in plans for action in plan.actions
        if action != RecoveryAction.COMPLETED
    )
    return RecoveryDashboard(
        owner_id=owner_id,
        total_unfinished=len(plans),
        blocked=sum(plan.blocked for plan in plans),
        actionable=sum(bool(plan.resumable_job_ids) for plan in plans),
        action_counts=dict(sorted(counts.items())),
        plans=plans,
    )


async def load_recovery_dashboard(
    *, owner_id: int, limit: int = 50,
) -> RecoveryDashboard:
    """Inspect a bounded batch; do not start jobs or resend documents."""
    checkpoints = await list_unfinished_checkpoints(
        owner_id=owner_id, limit=limit,
    )
    plans = [
        await plan_owned_recovery(
            owner_id=owner_id, story_id=checkpoint.story_id,
        )
        for checkpoint in checkpoints
    ]
    return summarize_recovery(owner_id=owner_id, plans=plans)
