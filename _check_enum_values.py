import asyncio
from sqlalchemy import text
from app.database.session import engine


QUERIES = {
    "customers.language": """
        SELECT language, COUNT(*)
        FROM customers
        GROUP BY language
        ORDER BY language
    """,
    "menu_items.category": """
        SELECT category, COUNT(*)
        FROM menu_items
        GROUP BY category
        ORDER BY category
    """,
    "menu_items.generation_status": """
        SELECT generation_status, COUNT(*)
        FROM menu_items
        GROUP BY generation_status
        ORDER BY generation_status
    """,
    "generated_files.kind": """
        SELECT kind, COUNT(*)
        FROM generated_files
        GROUP BY kind
        ORDER BY kind
    """,
}


async def main():
    async with engine.connect() as connection:
        for title, query in QUERIES.items():
            print(f"\n--- {title} ---")
            result = await connection.execute(text(query))
            for row in result:
                print(row)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())