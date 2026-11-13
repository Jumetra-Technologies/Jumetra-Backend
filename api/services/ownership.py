"""Who owns each Phase One object: Hybrid experiments, engineering workspaces
and laboratories. (Firmware projects keep their owner in their own metadata,
engine/firmware/firmware_studio.py, with the same rules.)

These objects live in process-wide services keyed only by id, so before this
module any signed-in person could read, change or delete anyone's, and every
list route (open to signed-out visitors, like every GET) returned everyone's,
firmware source code included (audit ENG-002, 13 Nov 2026).

Now every create records its owner here, lists show only the caller's own,
and an id that belongs to someone else answers 404, as if it didn't exist.
The record is a small JSON file in the data folder, written atomically.

With ``HHIP_REQUIRE_AUTH=false`` (local development and most tests) a
signed-out caller is the single local owner ``"local"``.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

from fastapi import HTTPException
from starlette.requests import HTTPConnection

LOCAL_OWNER = "local"

HYBRID = "hybrid"
WORKSPACE = "workspace"
LABORATORY = "laboratory"


class Owners:
    """kind -> id -> owner id, kept in ``<data dir>/owners.json``."""

    def __init__(self, path: Optional[Path]) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._owners: dict[str, dict[str, str]] = {}
        if path is not None and path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._owners = {
                        str(kind): {str(k): str(v) for k, v in ids.items()}
                        for kind, ids in raw.items()
                        if isinstance(ids, dict)
                    }
            except (OSError, ValueError):
                self._owners = {}

    def claim(self, kind: str, object_id: str, owner: str) -> None:
        with self._lock:
            self._owners.setdefault(kind, {})[object_id] = owner
            self._save()

    def owner_of(self, kind: str, object_id: str) -> Optional[str]:
        with self._lock:
            return self._owners.get(kind, {}).get(object_id)

    def owns(self, kind: str, object_id: str, owner: str) -> bool:
        return bool(object_id) and self.owner_of(kind, object_id) == owner

    def forget(self, kind: str, object_id: str) -> None:
        with self._lock:
            if self._owners.get(kind, {}).pop(object_id, None) is not None:
                self._save()

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".owners-", dir=str(self._path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._owners, f)
            os.replace(tmp, self._path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def owners(request: HTTPConnection) -> Owners:
    return request.app.state.owners


def caller(request: HTTPConnection) -> str:
    """The caller's owner id: the signed-in account, or "local" when sign-in isn't required.

    Resolved without rotating anything (a valid access token, else a valid refresh cookie),
    so it's safe to run before the route's own sign-in handling. 401 when sign-in is
    required and the caller isn't signed in.
    """
    from api.routes.telemetry import signed_in_user  # imported late: it imports this package

    user_id = signed_in_user(request)  # type: ignore[arg-type]
    if user_id:
        return user_id
    if getattr(request.app.state, "require_auth", True):
        raise HTTPException(status_code=401, detail="Sign in to use this.")
    return LOCAL_OWNER


class OwnedBy:
    """A router dependency: sign-in for every route, and the object in the path must be the caller's.

    ``param`` names the path parameter holding the object's id. ``public`` lists route paths
    (relative to the router, e.g. ``"/templates"``) that stay open to everyone. The caller's
    owner id is left on ``request.state.owner`` for create and list routes. WebSocket routes
    check their own ticket and ownership (see ``security.websocket_auth``).
    """

    def __init__(self, kind: str, param: str, *, public: Iterable[str] = ()) -> None:
        self.kind = kind
        self.param = param
        self.public = tuple(public)

    def __call__(self, request: HTTPConnection) -> None:
        if request.scope.get("type") != "http":
            return
        route = request.scope.get("route")
        path = getattr(route, "path", "")
        if any(path.endswith(p) for p in self.public):
            return
        owner = caller(request)
        request.state.owner = owner
        object_id = request.path_params.get(self.param)
        if object_id:
            require_owned(request, self.kind, object_id, owner)


def require_owned(request: HTTPConnection, kind: str, object_id: str, owner: str) -> None:
    """404 unless ``owner`` owns the object: someone else's id looks like a missing one."""
    if not owners(request).owns(kind, object_id, owner):
        raise HTTPException(status_code=404, detail="Not found.")


def claim_from(request: HTTPConnection, kind: str, owner: str, result: Any, keys: Iterable[str]) -> Any:
    """Record the owner of an object a create route just made, by the first id key it carries."""
    if isinstance(result, dict):
        for key in keys:
            value = result.get(key)
            if isinstance(value, str) and value:
                owners(request).claim(kind, value, owner)
                break
    return result


def own_only(request: HTTPConnection, kind: str, owner: str, items: Iterable[Any], keys: Iterable[str]) -> list[Any]:
    """The items of a list route that ``owner`` owns."""
    keys = tuple(keys)
    store = owners(request)
    kept = []
    for item in items:
        if not isinstance(item, dict):
            continue
        object_id = next((item.get(k) for k in keys if isinstance(item.get(k), str) and item.get(k)), None)
        if object_id and store.owns(kind, object_id, owner):
            kept.append(item)
    return kept
