"""Database initialization and session management."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .base import Base
from .enums import Role
from .models import Organization, PlatformExperiment, Project, User


def get_database_url(data_dir: Path | str) -> str:
    db_path = Path(data_dir) / "platform.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"


def init_db(data_dir: Path | str) -> sessionmaker[Session]:
    engine = create_engine(get_database_url(data_dir), connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
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
