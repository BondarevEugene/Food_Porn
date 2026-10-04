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

from app.database.models import Base as Base
