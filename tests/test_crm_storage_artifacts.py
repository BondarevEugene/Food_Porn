"""Artifact registry contracts: protected-by-default, immutable ownership."""
import pytest
from sqlalchemy.dialects import postgresql

from app.crm.storage_artifacts import artifacts, register


def test_registry_schema_protects_objects_by_default():
    assert artifacts.c.state.server_default.arg == "protected"
    assert artifacts.c.retention_hold.server_default is not None
    ddl = str(artifacts.insert().compile(dialect=postgresql.dialect()))
    assert "crm_storage_artifacts" in ddl


@pytest.mark.asyncio
async def test_registration_rejects_missing_identity_before_io():
    with pytest.raises(ValueError):
        await register(
            None, bot_id="little_legend", connection="release",
            bucket="private", object_key="", order_type="story",
            order_id="12", kind="pdf", bytes_count=42,
        )


@pytest.mark.asyncio
async def test_registration_rejects_negative_size_before_io():
    with pytest.raises(ValueError):
        await register(
            None, bot_id="little_legend", connection="release",
            bucket="private", object_key="books/12.pdf", order_type="story",
            order_id="12", kind="pdf", bytes_count=-1,
        )
