# app/services/pricing_service.py
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from src.billing.models import ProductPrice


async def get_current_price(db: AsyncSession, product_key: str = "collage_uah") -> float:
    """
    Возвращает актуальную цену продукта на текущую дату и время из базы данных.
    """
    now = datetime.utcnow()
    query = (
        select(ProductPrice)
        .where(ProductPrice.product_key == product_key)
        .where(ProductPrice.effective_from <= now)
        .order_by(desc(ProductPrice.effective_from))
        .limit(1)
    )
    result = await db.scalar(query)
    if result:
        return result.price_value
    return 500.0  # Дефолтная стоимость


async def set_scheduled_price(
    db: AsyncSession,
    price_value: float,
    effective_from: datetime,
    product_key: str = "collage_uah"
) -> ProductPrice:
    """
    Устанавливает новую цену продукта, которая начнет действовать с указанной даты.
    """
    new_price = ProductPrice(
        product_key=product_key,
        price_value=price_value,
        effective_from=effective_from
    )
    db.add(new_price)
    await db.commit()
    await db.refresh(new_price)
    return new_price
