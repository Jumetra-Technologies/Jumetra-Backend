from dataclasses import dataclass
@dataclass(frozen=True)
class SessionCookieConfig:
    name: str = "hhip_session"
    secure: bool = True
    httponly: bool = True
    samesite: str = "lax"
    path: str = "/"
