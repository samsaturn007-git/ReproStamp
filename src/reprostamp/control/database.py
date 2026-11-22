from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg.rows import dict_row
from sqlalchemy import create_engine

from .settings import Settings


def connect(settings: Settings):
    return psycopg.connect(settings.dsn, row_factory=dict_row, connect_timeout=3,
                           options="-c statement_timeout=5000 -c idle_in_transaction_session_timeout=120000")


def migrate(settings: Settings) -> None:
    engine = create_engine("postgresql+psycopg://", creator=lambda: psycopg.connect(settings.dsn))
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(100367031)")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()
