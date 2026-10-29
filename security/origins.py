from __future__ import annotations

import re


def is_allowed_origin(origin: str | None, allowed: list[str], pattern: str) -> bool:
    if not origin:
        return False
    return origin in allowed or re.fullmatch(pattern, origin) is not None