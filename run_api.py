#!/usr/bin/env python3
"""Start the HHIP FastAPI platform API.

Run from anywhere::

    python hhip/run_api.py

Or from ``hhip/``::

    python run_api.py
"""

from __future__ import annotations

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
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(_HHIP_ROOT)],
    )
