"""HHIP platform database models — schema foundation for multi-tenant research."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import Role


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    projects: Mapped[list["Project"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default=Role.RESEARCHER.value)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    organization: Mapped["Organization"] = relationship(back_populates="users")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    organization: Mapped["Organization"] = relationship(back_populates="projects")
    experiments: Mapped[list["PlatformExperiment"]] = relationship(back_populates="project")


class PlatformExperiment(Base):
    """Platform experiment record — links research workspace to engine ``EXP###`` runs."""

    __tablename__ = "platform_experiments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    strategy: Mapped[str] = mapped_column(String(32), default="fixed")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    project: Mapped["Project"] = relationship(back_populates="experiments")
