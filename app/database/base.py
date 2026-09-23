"""
==========================================================
FOOD_PORN

Module: SQLAlchemy Declarative Base
Layer: Persistence

Responsibilities:
    - Provide the shared declarative base for ORM models
    - Supply metadata to Alembic migrations
==========================================================
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
