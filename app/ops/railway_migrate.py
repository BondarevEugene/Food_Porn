"""Explicit, observable Alembic migration entry point for Railway.

Run only in the designated Railway pre-deploy step, never in worker polling.
"""
from __future__ import annotations

import logging
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("food_porn.migrations")


def main() -> int:
    url = get_settings().database_url
    parsed = make_url(url)
    # No credentials, hostname, database URL or connection parameters in logs.
    logger.info("MIGRATION_START driver=%s", parsed.drivername)
    config = Config("alembic.ini")
    try:
        command.current(config, verbose=True)
        command.upgrade(config, "head")
        command.current(config, verbose=True)
    except Exception:
        logger.exception("MIGRATION_FAILED; worker must not start")
        return 1
    logger.info("MIGRATION_SUCCESS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
