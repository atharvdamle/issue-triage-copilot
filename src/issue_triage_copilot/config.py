"""Project configuration. The only place environment variables are read."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    github_token: str | None = None
    github_repo: str = "microsoft/vscode"
    database_url: str = "postgresql://triage:triage@localhost:5432/triage"
    raw_data_dir: Path = PROJECT_ROOT / "data" / "raw"
    reports_dir: Path = PROJECT_ROOT / "reports"


settings = Settings()
