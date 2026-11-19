"""Worker dispatch integration requires budgeted effect fencing."""
from pathlib import Path

from app.little_legend.production_effect_ledger import EffectKind
from app.little_legend.worker_ai_fence import fence_worker_ai_effect


def test_worker_fence_is_async_and_accepts_both_ai_kinds():
    import inspect

    assert inspect.iscoroutinefunction(fence_worker_ai_effect)
    assert EffectKind.WRITER_AI.value == "writer_ai"
    assert EffectKind.ILLUSTRATION_AI.value == "illustration_ai"


def test_writer_dispatch_calls_budget_fence_before_marker():
    source = Path("app/little_legend/writer_queue_store.py").read_text(
        encoding="utf-8",
    )
    function = source.split("async def mark_writer_provider_dispatched(", 1)[1]
    function = function.split("async def transition_writer_job(", 1)[0]
    assert function.index("await fence_worker_ai_effect(") < (
        function.index('job.model_copy(update={"provider_dispatched_at": now})')
    )


def test_illustration_dispatch_calls_budget_fence_after_consent_check():
    source = Path("app/little_legend/illustration_queue_store.py").read_text(
        encoding="utf-8",
    )
    function = source.split("async def fence_illustration_dispatch(", 1)[1]
    function = function.split("async def complete_illustration_job(", 1)[0]
    assert function.index("consent_allows_image_ai(") < (
        function.index("await fence_worker_ai_effect(")
    )
    assert function.index("await fence_worker_ai_effect(") < (
        function.index('job.model_copy(update={"provider_dispatched_at": now})')
    )
