from __future__ import annotations

from fastapi import WebSocket

from auth.tokens import decode_websocket_ticket
from database.service import consume_websocket_ticket
from .origins import is_allowed_origin


def authenticate_websocket(websocket: WebSocket) -> bool:
    if not websocket.app.state.require_auth:
        return True

    origin = websocket.headers.get("origin")
    if not is_allowed_origin(
        origin,
        websocket.app.state.allowed_origins,
        websocket.app.state.origin_pattern,
    ):
        return False

    ticket = websocket.query_params.get("ticket")
    if not ticket:
        return False
    try:
        payload = decode_websocket_ticket(ticket, websocket.app.state.session_secret)
    except Exception:
        return False

    with websocket.app.state.db_factory() as session:
        return consume_websocket_ticket(
            session,
            jti=str(payload.get("jti", "")),
            user_id=str(payload.get("sub", "")),
        )