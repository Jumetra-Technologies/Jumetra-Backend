"""Deterministic package checksums."""
from __future__ import annotations
import hashlib
from pathlib import Path

class ChecksumVerifier:
    filename = "checksum.sha256"

    @classmethod
    def calculate(cls, package: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted((p for p in package.rglob("*") if p.is_file() and p.name != cls.filename), key=lambda p: p.relative_to(package).as_posix()):
            digest.update(path.relative_to(package).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    @classmethod
    def verify(cls, package: Path) -> tuple[bool, str]:
        path = package / cls.filename
        if not path.exists():
            return False, "checksum.sha256 is missing"
        expected = path.read_text(encoding="utf-8").strip().split()[0].lower()
        actual = cls.calculate(package)
        return actual == expected, actual
