"""SQLAlchemy declarative base for HHIP platform schema."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all platform ORM models."""
