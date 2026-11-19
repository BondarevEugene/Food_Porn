"""Durable checkpoint schema and recovery contract."""
from sqlalchemy import BigInteger, Integer
from sqlalchemy.dialects import postgresql

from app.little_legend.production_checkpoint import (
    ProductionCheckpoint, ProductionPhase,
)
from app.little_legend.production_checkpoint_store import (
    _decode, production_checkpoints,
)


def test_checkpoint_table_has_unique_story_and_owner_scope():
    table = production_checkpoints
    assert table.primary_key.columns.keys() == ["story_id"]
    assert table.c.owner_id.type.__class__ is BigInteger
    assert table.c.story_id.type.__class__ is Integer
    assert table.c.story_id.foreign_keys
    assert table.c.version.nullable is False
    assert table.c.phase.nullable is False


def test_database_row_round_trip_restores_checkpoint():
    checkpoint = ProductionCheckpoint(
        owner_id=3, story_id=2, version=4,
        phase=ProductionPhase.DELIVERY_PENDING,
        release_fingerprint="a" * 64, pdf_sha256="b" * 64,
    )
    row = checkpoint.model_dump(mode="python")
    restored = _decode(row)
    assert restored == checkpoint


def test_checkpoint_schema_compiles_for_neon_postgresql():
    from sqlalchemy.schema import CreateTable

    sql = str(CreateTable(production_checkpoints).compile(
        dialect=postgresql.dialect(),
    ))
    assert "little_legend_production_checkpoints" in sql
    assert "FOREIGN KEY(story_id)" in sql
    assert "ON DELETE CASCADE" in sql
    assert "PRIMARY KEY (story_id)" in sql


def test_checkpoint_validation_rejects_invalid_fingerprint():
    import pytest

    with pytest.raises(ValueError):
        ProductionCheckpoint(
            owner_id=3, story_id=2, release_fingerprint="invalid",
        )
