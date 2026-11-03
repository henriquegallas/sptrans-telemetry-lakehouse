"""Collector settings.

Precedence, highest first: process environment, `.env` (secrets, git-ignored), then
`config/<ENV>.env` (non-secret settings per environment, committed).
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENVIRONMENTS = ("local", "aws")


class CollectorSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    api_base_url: HttpUrl = Field(alias="SPTRANS_API_BASE_URL")
    api_token: SecretStr = Field(alias="SPTRANS_API_TOKEN", min_length=1)
    raw_dir: Path = Field(alias="COLLECTOR_RAW_DIR")
    poll_interval_seconds: float = Field(60.0, gt=0, alias="COLLECTOR_POLL_INTERVAL_SECONDS")
    request_timeout_seconds: float = Field(20.0, gt=0, alias="COLLECTOR_REQUEST_TIMEOUT_SECONDS")
    max_attempts: int = Field(5, ge=1, alias="COLLECTOR_MAX_ATTEMPTS")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        "INFO", alias="COLLECTOR_LOG_LEVEL"
    )


def settings_files(dotenv: Path = Path(".env")) -> tuple[Path, Path]:
    """Files to read, lowest precedence first."""
    # ENV picks the config file, so it has to be resolved before pydantic reads any file.
    env = os.environ.get("ENV") or dotenv_values(dotenv).get("ENV") or "local"
    if env not in ENVIRONMENTS:
        raise ValueError(f"ENV must be one of {ENVIRONMENTS}, got {env!r}")
    return Path("config") / f"{env}.env", dotenv


def load_settings() -> CollectorSettings:
    return CollectorSettings(_env_file=settings_files())
