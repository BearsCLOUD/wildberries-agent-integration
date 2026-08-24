from __future__ import annotations

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True, slots=True)
class Settings:
    """Environment-backed settings with a fail-closed production default."""

    gateway_url: str = ""
    connect_url: str = ""
    timeout_seconds: float = 20.0
    environment: str = "development"
    static_access_token: str = ""
    host: str = "127.0.0.1"
    port: int = 8080

    @classmethod
    def from_env(cls) -> "Settings":
        timeout_raw = getenv("SELLER_GATEWAY_TIMEOUT_SECONDS", "20")
        try:
            timeout_seconds = max(1.0, min(float(timeout_raw), 120.0))
        except ValueError:
            timeout_seconds = 20.0

        port_raw = getenv("PORT", "8080")
        try:
            port = max(1, min(int(port_raw), 65535))
        except ValueError:
            port = 8080

        return cls(
            gateway_url=getenv("SELLER_GATEWAY_URL", "").rstrip("/"),
            connect_url=getenv("SELLER_CONNECT_URL", "").strip(),
            timeout_seconds=timeout_seconds,
            environment=getenv("APP_ENV", "development").lower().strip(),
            static_access_token=getenv("SELLER_ACCESS_TOKEN", ""),
            host=getenv("HOST", "127.0.0.1"),
            port=port,
        )

    @property
    def allows_static_token(self) -> bool:
        return self.environment in {"development", "dev", "test"}
