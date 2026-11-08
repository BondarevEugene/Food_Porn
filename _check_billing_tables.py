import asyncio
from sqlalchemy import text
from app.database.session import engine

async def main():
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = :schema ORDER BY table_name"),
            {"schema": "public"},
        )
        names = [row[0] for row in result]
        for name in ("accounts", "transactions", "menus", "menu_items", "payments"):
            print(f"{name}: {'EXISTS' if name in names else 'not found'}")
    await engine.dispose()

asyncio.run(main())
