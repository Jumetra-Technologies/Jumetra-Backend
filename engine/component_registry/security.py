"""Trust policy for component packages; no code execution is permitted here."""
from __future__ import annotations
from enum import Enum
from pathlib import Path
from .checksum import ChecksumVerifier

class TrustLevel(str, Enum):
    OFFICIAL = "official"
    COMMUNITY = "community"
    LOCAL = "local"
    UNVERIFIED = "unverified"

class ComponentSecurityManager:
    def verify(self, package: Path, source: str, declared_trust: str) -> tuple[bool, str, str]:
        try:
            level = TrustLevel(declared_trust.lower())
        except ValueError:
            return False, "unverified", "invalid trust level"
        if source == "official":
            if level is not TrustLevel.OFFICIAL:
                return False, level.value, "official packages must declare official trust"
            ok, detail = ChecksumVerifier.verify(package)
            return ok, level.value, "" if ok else f"checksum verification failed: {detail}"
        if source == "community":
            return level in (TrustLevel.COMMUNITY, TrustLevel.LOCAL), level.value, "community packages must declare community or local trust"
        # Marketplace packages need a future signature/transparency-log check.
        return False, level.value, "unverified marketplace package is not auto-loaded"
