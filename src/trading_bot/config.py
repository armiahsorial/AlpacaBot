"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_BASE_URL = "https://api.gexbot.com"
DEFAULT_USER_AGENT = "trading_bot/0.1.0"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_ENV_FILE = Path.cwd() / ".env"


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls, env_file: Path | str | None = DEFAULT_ENV_FILE) -> "Settings":
        values = _load_env_file(env_file)
        values.update(os.environ)

        api_key = values.get("GEX_API_KEY", "").strip()
        if not api_key:
            raise ValueError("GEX_API_KEY is required.")

        base_url = values.get("GEX_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
        user_agent = values.get("GEX_USER_AGENT", DEFAULT_USER_AGENT).strip()
        timeout_raw = values.get("GEX_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)).strip()

        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise ValueError("GEX_TIMEOUT_SECONDS must be a number.") from exc

        if timeout_seconds <= 0:
            raise ValueError("GEX_TIMEOUT_SECONDS must be greater than zero.")

        return cls(
            api_key=api_key,
            base_url=base_url,
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
        )


def _load_env_file(env_file: Path | str | None) -> dict[str, str]:
    if env_file is None:
        return {}

    path = Path(env_file)
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("export "):
            stripped = stripped.removeprefix("export ").strip()

        key, separator, value = stripped.partition("=")
        if not separator:
            continue

        key = key.strip()
        if not key:
            continue

        values[key] = _clean_env_value(value)

    return values


def _clean_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
