"""Align historic enum columns and persist menu/wallpaper payment snapshots.

Revision ID: 20260928_0003
Revises: ffb74d9cb65b
"""
from alembic import op

revision = "20260928_0003"
down_revision = "ffb74d9cb65b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Initial migrations created native PostgreSQL enums. The current ORM
    # stores names in VARCHAR; convert before writing newer workflow values.
    for table, column in (
        ("customers", "language"),
        ("menus", "status"),
        ("menu_items", "category"),
        ("menu_items", "generation_status"),
        ("generated_files", "kind"),
    ):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE VARCHAR(30) USING {column}::text")
    op.execute("UPDATE menus SET status = 'QUEUED' WHERE status = 'GENERATING'")
    op.execute("UPDATE menus SET status = 'IMAGES_READY' WHERE status = 'RENDERING'")
    op.execute("UPDATE menus SET status = 'COMPLETED' WHERE status = 'COMPLETE'")
    # Older schemas require the obsolete menus.language column, while the
    # current ORM no longer supplies it when inserting new menus.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'menus' AND column_name = 'language') THEN
                EXECUTE 'ALTER TABLE menus ALTER COLUMN language SET DEFAULT ''UK''';
            END IF;
        END $$
    """)

    op.execute("ALTER TABLE menus ADD COLUMN IF NOT EXISTS price_amount NUMERIC(10, 2)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key VARCHAR(100) PRIMARY KEY, value TEXT NOT NULL, description TEXT
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS wallpaper_orders (
            id SERIAL PRIMARY KEY,
            telegram_user_id BIGINT NOT NULL,
            amount NUMERIC(10, 2) NOT NULL,
            mobile_path TEXT NOT NULL,
            desktop_path TEXT NOT NULL,
            paid BOOLEAN NOT NULL DEFAULT false,
            payment_id VARCHAR(100),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wallpaper_orders_telegram_user_id ON wallpaper_orders (telegram_user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_customers_telegram_user_id ON customers (telegram_user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_image_cache_cache_key ON image_cache (cache_key)")


def downgrade() -> None:
    raise RuntimeError("Downgrade would delete order/payment data; restore a database backup instead")
