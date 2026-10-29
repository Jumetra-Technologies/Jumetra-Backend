"""Alembic environment. Run `alembic upgrade head` with DATABASE_URL set, or
let the server do it on startup (api/db/init_db.py)."""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from api.db.base import Base
import api.db.models  # noqa: F401  registers the platform tables
import database.models  # noqa: F401  registers the identity and account tables

config = context.config
# The command line gets alembic.ini's logging. The server (init_db) keeps its own.
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    from api.db.init_db import get_database_url

    return get_database_url(os.environ.get("HHIP_DATA_DIR") or Path(__file__).resolve().parents[1] / "data")


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # render_as_batch lets ALTER TABLE work on SQLite too.
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
