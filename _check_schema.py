import asyncio
from sqlalchemy import text
from app.database.session import engine


async def main():
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))

            tables = result.scalars().all()

            print("DATABASE TABLES:")
            for table in tables:
                print(" -", table)

            print("TOTAL:", len(tables))

    except Exception as exc:
        print("ERROR:", type(exc).__name__, str(exc))

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())