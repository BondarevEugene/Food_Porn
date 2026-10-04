import asyncio
from app.database.session import engine
from src.billing.models import Base

async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Tables created successfully!')

asyncio.run(init())
