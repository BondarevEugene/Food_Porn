import asyncio
from sqlalchemy import inspect
from app.database.session import engine


TABLES = [
    "customers",
    "menus",
    "menu_items",
    "portmone_sandbox_payments",
    "wayforpay_payments",
    "wallpaper_orders",
    "wallpaper_exports",
    "wallpaper_scene_versions",
    "generated_files",
    "ai_generation_logs",
    "provider_costs",
]


def inspect_schema(connection):
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())

    for table in TABLES:
        print(f"\n{'=' * 55}")
        print(f"TABLE: {table}")

        if table not in existing:
            print("NOT FOUND")
            continue

        print("COLUMNS:")
        for column in inspector.get_columns(table):
            nullable = "NULL" if column["nullable"] else "NOT NULL"
            print(f"  {column['name']} | {column['type']} | {nullable}")

        print("FOREIGN KEYS:")
        foreign_keys = inspector.get_foreign_keys(table)

        if not foreign_keys:
            print("  None")

        for fk in foreign_keys:
            print(
                f"  {fk['constrained_columns']} -> "
                f"{fk['referred_table']}.{fk['referred_columns']}"
            )


async def main():
    try:
        async with engine.connect() as connection:
            await connection.run_sync(inspect_schema)
    except Exception as exc:
        print("SCHEMA INSPECTION FAILED:")
        print(type(exc).__name__, str(exc))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())