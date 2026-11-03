from pathlib import Path

import pytest
from pydantic import ValidationError

from collector.config import load_settings

SETTINGS_VARS = (
    "ENV",
    "SPTRANS_API_BASE_URL",
    "SPTRANS_API_TOKEN",
    "COLLECTOR_RAW_DIR",
    "COLLECTOR_POLL_INTERVAL_SECONDS",
    "COLLECTOR_REQUEST_TIMEOUT_SECONDS",
    "COLLECTOR_MAX_ATTEMPTS",
    "COLLECTOR_LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def project_dir(monkeypatch, tmp_path):
    """Run each test in an empty project dir so the developer's real .env is never read."""
    for var in SETTINGS_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    return tmp_path


def write_env(path: Path, **values: str) -> None:
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))


@pytest.fixture
def local_config(project_dir):
    write_env(
        project_dir / "config" / "local.env",
        SPTRANS_API_BASE_URL="https://api.example.test/v2.1",
        COLLECTOR_RAW_DIR="data/raw",
    )
    write_env(project_dir / ".env", SPTRANS_API_TOKEN="secret-token")


@pytest.mark.usefixtures("local_config")
def test_combines_config_file_and_dotenv_secrets():
    settings = load_settings()

    assert str(settings.api_base_url) == "https://api.example.test/v2.1"
    assert settings.raw_dir == Path("data/raw")
    assert settings.api_token.get_secret_value() == "secret-token"
    assert settings.poll_interval_seconds == 60


@pytest.mark.usefixtures("local_config")
def test_process_env_beats_dotenv_which_beats_config_file(project_dir, monkeypatch):
    write_env(project_dir / ".env", SPTRANS_API_TOKEN="secret-token", COLLECTOR_RAW_DIR="dotenv")
    assert load_settings().raw_dir == Path("dotenv")

    monkeypatch.setenv("COLLECTOR_RAW_DIR", "/data/raw")
    assert load_settings().raw_dir == Path("/data/raw")


def test_env_in_dotenv_selects_the_config_file(project_dir):
    write_env(
        project_dir / "config" / "aws.env",
        SPTRANS_API_BASE_URL="https://api.example.test/v2.1",
        COLLECTOR_RAW_DIR="/aws/raw",
    )
    write_env(project_dir / ".env", ENV="aws", SPTRANS_API_TOKEN="secret-token")

    assert load_settings().raw_dir == Path("/aws/raw")


def test_unknown_env_is_rejected(monkeypatch):
    monkeypatch.setenv("ENV", "prod")

    with pytest.raises(ValueError, match="ENV must be one of"):
        load_settings()


def test_missing_token_fails_fast(project_dir):
    write_env(
        project_dir / "config" / "local.env",
        SPTRANS_API_BASE_URL="https://api.example.test/v2.1",
        COLLECTOR_RAW_DIR="data/raw",
    )

    with pytest.raises(ValidationError, match="SPTRANS_API_TOKEN"):
        load_settings()


@pytest.mark.usefixtures("local_config")
def test_token_is_masked_in_repr():
    assert "secret-token" not in repr(load_settings())
