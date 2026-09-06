from dataclasses import dataclass
@dataclass(frozen=True)
class CSRFConfig:
    header_name: str = "X-CSRF-Token"
    cookie_name: str = "hhip_csrf"
    enabled: bool = False
