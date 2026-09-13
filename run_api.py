#!/usr/bin/env python3
"""Start the HHIP FastAPI platform API.

Run from anywhere::

    python hhip/run_api.py

Or from ``hhip/``::

    python run_api.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure ``hhip/`` is on sys.path so ``api`` and ``engine`` import correctly.
_HHIP_ROOT = Path(__file__).resolve().parent
if str(_HHIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_HHIP_ROOT))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        reload=os.environ.get("UVICORN_RELOAD", "").lower() in {"1", "true", "yes"},
    )
