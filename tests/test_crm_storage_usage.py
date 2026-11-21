"""Storage usage totals must remain accurate when providers fail."""
from app.crm.storage_usage import summarize


def connection(bot, bucket, *, status="ok", used=100, count=2):
    return {
        "bot_id": bot, "storage_provider": "S3-compatible",
        "bucket": bucket, "status": status,
        "used_bytes": used if status == "ok" else None,
        "object_count": count if status == "ok" else None,
    }


def test_shared_bucket_groups_disjoint_bot_usage():
    result = summarize([
        connection("bot_a", "shared", used=100),
        connection("bot_b", "shared", used=300),
    ])
    assert len(result["bucket_usage"]) == 1
    assert result["bucket_usage"][0]["used_bytes"] == 400
    assert result["bucket_usage"][0]["bots"] == ["bot_a", "bot_b"]
    assert [row["used_bytes"] for row in result["bot_usage"]] == [100, 300]


def test_failed_connection_does_not_become_zero_or_break_later_success():
    result = summarize([
        connection("bot_a", "shared", status="error"),
        connection("bot_a", "other", used=250),
        connection("bot_b", "shared", used=300),
    ])
    bot = next(x for x in result["bot_usage"] if x["bot_id"] == "bot_a")
    assert bot["status"] == "partial"
    assert bot["used_bytes"] is None
    assert bot["object_count"] is None
    bucket = next(x for x in result["bucket_usage"] if x["bucket"] == "shared")
    assert bucket["used_bytes"] is None
    assert bucket["object_count"] is None


def test_empty_registry_returns_empty_summary():
    assert summarize([]) == {"bot_usage": [], "bucket_usage": []}
