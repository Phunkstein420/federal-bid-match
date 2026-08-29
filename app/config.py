"""Runtime configuration from environment names only. Never log secret values."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


class MissingEnvError(RuntimeError):
    """Required environment variable is unset."""


def _optional(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def require_env(name: str) -> str:
    value = _optional(name)
    if value is None:
        raise MissingEnvError(f"{name} is not set")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    api_key: str | None
    sam_api_key: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=_optional("DATABASE_URL"),
            api_key=_optional("API_KEY"),
            sam_api_key=_optional("SAM_API_KEY"),
        )

    def require_database_url(self) -> str:
        if not self.database_url:
            raise MissingEnvError("DATABASE_URL is not set")
        return self.database_url
