"""Перевірка повного ланцюга Alembic лише в окремій порожній тестовій БД.

Встановіть FOOD_PORN_MIGRATIONS_TEST_DATABASE_URL на нову БД
з точним ім'ям food_porn_migrations_test. Робочу БД скрипт не змінює.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

EXPECTED_DATABASE = "food_porn_migrations_test"
EXPECTED_HEAD = "20261109_0014"


async def _inspect_database(raw_url: str, *, expect_empty: bool) -> None:
    parsed = make_url(raw_url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != EXPECTED_DATABASE:
        raise RuntimeError(
            "Відмовлено: потрібна окрема PostgreSQL БД food_porn_migrations_test"
        )
    normalized = parsed.set(drivername="postgresql+asyncpg").difference_update_query(
        ["sslmode", "channel_binding"]
    )
    engine = create_async_engine(normalized, connect_args={"ssl": "require"})
    try:
        async with engine.connect() as connection:
            actual_database = await connection.scalar(text("SELECT current_database()"))
            if actual_database != EXPECTED_DATABASE:
                raise RuntimeError("Підключення вказує на неочікувану базу даних")
            if expect_empty:
                tables = (
                    await connection.execute(
                        text(
                            "SELECT tablename FROM pg_catalog.pg_tables "
                            "WHERE schemaname = 'public'"
                        )
                    )
                ).scalars().all()
                if tables:
                    raise RuntimeError(
                        "Відмовлено: тестова БД не порожня; "
                        "створіть нову порожню базу"
                    )
            else:
                version = await connection.scalar(
                    text("SELECT version_num FROM public.alembic_version")
                )
                if version != EXPECTED_HEAD:
                    raise RuntimeError(
                        f"Невірна кінцева ревізія: {version!r}, "
                        f"очікується {EXPECTED_HEAD}"
                    )
    finally:
        await engine.dispose()


def main() -> int:
    raw_url = os.environ.get("FOOD_PORN_MIGRATIONS_TEST_DATABASE_URL", "").strip()
    if not raw_url:
        print("Встановіть FOOD_PORN_MIGRATIONS_TEST_DATABASE_URL для нової тестової БД.")
        return 2
    try:
        parsed = make_url(raw_url)
    except ArgumentError:
        print(
            "Некоректний URL. Очікується формат "
            "postgresql://USER:PASSWORD@HOST/food_porn_migrations_test?sslmode=require. "
            "Не публікуйте пароль у повідомленнях або журналах."
        )
        return 2
    if parsed.get_backend_name() != "postgresql" or parsed.database != EXPECTED_DATABASE:
        print("Відмовлено: назва БД має бути рівно food_porn_migrations_test.")
        return 2

    asyncio.run(_inspect_database(raw_url, expect_empty=True))
    environment = os.environ.copy()
    environment["DATABASE_URL"] = (
        parsed.set(drivername="postgresql+asyncpg")
        .difference_update_query(["sslmode", "channel_binding"])
        .render_as_string(hide_password=False)
    )
    # Alembic env.py бере адресу з Settings; змінна процесу має пріоритет над .env.
    print("Перевірено порожню тестову БД. Запускаємо Alembic upgrade head...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        print("Помилка міграцій. Тестова база збережена для діагностики.")
        return result.returncode
    asyncio.run(_inspect_database(raw_url, expect_empty=False))
    print(f"Успішно: тестова БД оновлена до {EXPECTED_HEAD}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
