"""Database setup: the URL, the engine, migrations and the seed rows.

The URL comes from ``DATABASE_URL`` (PostgreSQL on staging and production,
``postgresql+psycopg://user:pass@host/db``). Without it the server uses a
SQLite file under the data directory, which is fine for development, tests
and the Render disk the Phase One backend runs on.

Schema changes are Alembic migrations in ``alembic/versions``. ``init_db``
brings any database to the current head. The baseline migration creates only
what is missing, so a database created before Alembic (by ``create_all``)
keeps its tables and rows and picks up the columns it lacks.
"""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .enums import Role
from .models import Organization, PlatformExperiment, Project, User

_REPO_ROOT = Path(__file__).resolve().parents[2]


def get_database_url(data_dir: Path | str) -> str:
    env = os.environ.get("DATABASE_URL", "").strip()
    if env:
        if env.startswith("postgres://"):
            env = "postgresql+psycopg://" + env[len("postgres://"):]
        elif env.startswith("postgresql://"):
            env = "postgresql+psycopg://" + env[len("postgresql://"):]
        return env
    db_path = Path(data_dir) / "platform.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


def alembic_config(url: str) -> Config:
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    config.attributes["configure_logging"] = False
    return config


def migrate(engine: Engine, url: str) -> None:
    """Bring the database to the current head. The baseline migration keeps
    tables and rows a pre-migration database already has."""
    command.upgrade(alembic_config(url), "head")


def init_db(data_dir: Path | str) -> sessionmaker[Session]:
    url = get_database_url(data_dir)
    engine = make_engine(url)
    migrate(engine, url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    _seed_if_empty(factory)
    return factory


def _seed_if_empty(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        if session.scalar(select(Organization).limit(1)):
            return

        org = Organization(name="HHIP Research Lab", slug="hhip-lab")
        session.add(org)
        session.flush()

        admin = User(
            email="admin@hhip.local",
            display_name="Platform Admin",
            role=Role.ADMIN.value,
            organization_id=org.id,
        )
        researcher = User(
            email="researcher@hhip.local",
            display_name="Lead Researcher",
            role=Role.RESEARCHER.value,
            organization_id=org.id,
        )
        session.add_all([admin, researcher])
        session.flush()

        project = Project(
            name="Hybrid Sync Research",
            description="Fixed vs adaptive synchronization studies",
            organization_id=org.id,
            owner_id=researcher.id,
        )
        session.add(project)
        session.flush()

        session.add_all(
            [
                PlatformExperiment(
                    name="fixed_sync_baseline",
                    external_id="EXP_FIXED01",
                    strategy="fixed",
                    status="completed",
                    project_id=project.id,
                ),
                PlatformExperiment(
                    name="adaptive_sync_study",
                    external_id="EXP_ADAPT01",
                    strategy="adaptive",
                    status="completed",
                    project_id=project.id,
                ),
            ]
        )
        session.commit()
