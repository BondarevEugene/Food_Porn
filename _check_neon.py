import asyncio
from sqlalchemy import text
from app.database.session import engine


async def main():
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT version(), current_database(), current_user")
            )
            row = result.one()

            print("DATABASE CONNECTION: OK")
            print("DATABASE:", row[1])
            print("USER:", row[2])
            print("POSTGRES:", row[0].split(",")[0])

    except Exception as exc:
        print("DATABASE CONNECTION: FAILED")
        print(type(exc).__name__, str(exc))

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())