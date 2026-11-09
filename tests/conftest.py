import pytest
from sqlalchemy import event

from app.database.session import engine


@pytest.fixture(scope="session", autouse=True)
def trace_database_connections():
    def on_connect(dbapi_connection, connection_record):
        raise AssertionError("TEST SAFETY: Global PostgreSQL connection attempted")
    event.listen(engine.sync_engine, "connect", on_connect)
    try:
        yield
    finally:
        event.remove(engine.sync_engine, "connect", on_connect)
