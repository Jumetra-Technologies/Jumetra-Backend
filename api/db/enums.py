"""Platform role definitions — auth foundation only (no enforcement yet)."""

from enum import Enum


class Role(str, Enum):
    ADMIN = "ADMIN"
    RESEARCHER = "RESEARCHER"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"
    VIEWER = "VIEWER"
