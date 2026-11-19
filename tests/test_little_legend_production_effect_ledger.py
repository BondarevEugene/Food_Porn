"""Idempotency ledger contract and safe transitions."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import Column, Integer, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.little_legend.production_effect_ledger import (
    EffectKind,
    EffectStatus,
    ProductionEffect,
    _decode,
    production_effects,
    request_fingerprint,
)


def test_request_fingerprint_is_order_independent():
    assert request_fingerprint({"scene": 1, "revision": 2}) == (
        request_fingerprint({"revision": 2, "scene": 1})
    )


def test_changed_revision_changes_idempotency_digest():
    assert request_fingerprint({"revision": 1}) != (
        request_fingerprint({"revision": 2})
    )


def test_effect_row_round_trip():
    now = datetime.now(UTC)
    effect = ProductionEffect(
        effect_key="illustration:2:scene_1:rev1",
        owner_id=3, story_id=2, kind=EffectKind.ILLUSTRATION_AI,
        request_sha256="a" * 64, status=EffectStatus.UNCERTAIN,
        created_at=now, updated_at=now,
    )
    assert _decode(effect.model_dump(mode="python")) == effect


def test_invalid_digest_rejected():
    with pytest.raises(ValueError):
        ProductionEffect(
            effect_key="illustration:2:scene_1:rev1",
            owner_id=3, story_id=2, kind=EffectKind.ILLUSTRATION_AI,
            request_sha256="wrong",
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )


def test_effect_table_compiles_for_postgres():
    Table(
        "little_legend_stories", production_effects.metadata,
        Column("id", Integer, primary_key=True),
        extend_existing=True,
    )
    sql = str(CreateTable(production_effects).compile(
        dialect=postgresql.dialect(),
    ))
    assert "PRIMARY KEY (effect_key)" in sql
    assert "ON DELETE CASCADE" in sql


def test_effect_key_is_unique_and_owner_scoped():
    assert production_effects.primary_key.columns.keys() == ["effect_key"]
    assert production_effects.c.owner_id.nullable is False
    assert production_effects.c.story_id.foreign_keys
