"""Безпечний перехід історичної ревізії.

Revision ID: aa913e48a33c
Revises: 6579641ea68a

Початкова автогенерована міграція видаляла accounts і transactions,
хоча ці таблиці не створюються попередніми ревізіями. Видалення
фінансових таблиць із наявними даними також неприпустиме.
"""

from collections.abc import Sequence

revision: str = "aa913e48a33c"
down_revision: str | None = "6579641ea68a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Історичний маркер ревізії; жодних руйнівних змін фінансових таблиць.
    pass


def downgrade() -> None:
    # Ця ревізія не змінює схему, тому відкат також не змінює її.
    pass
