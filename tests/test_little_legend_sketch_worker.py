"""Worker rejects missing authorization before calling any provider."""
from types import SimpleNamespace

import pytest

from app.little_legend.sketch_worker import prepare_claimed_chapter
from app.little_legend.text_ai_consent import TextAIConsent
from app.little_legend.writer_queue import WriterJob


def test_preflight_blocks_missing_consent():
    job = WriterJob(
        job_id="ll_test_worker_job_12345", story_id=1, owner_id=1,
        scene_id="scene_1", expected_revision=0, estimated_cost_usd=0.05,
    )
    draft = SimpleNamespace(text_ai_consent=TextAIConsent())
    with pytest.raises(PermissionError, match="consent"):
        prepare_claimed_chapter(job, draft)
