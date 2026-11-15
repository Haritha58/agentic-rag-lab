from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Process-level configuration from environment / .env.

    User-editable preferences (weights, allocation, schedules) live in the
    `settings` DB table instead; see app/prefs.py.
    """

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://jobpilot:jobpilot@localhost:5433/jobpilot"
    data_dir: Path = PROJECT_ROOT / "data"
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"

    # LLM engine: "claude_code" (Pro plan via local `claude -p`) or "fake" (tests/offline).
    llm_engine: str = "claude_code"
    claude_bin: str = "claude"
    llm_timeout_s: int = 180

    @property
    def facts_file(self) -> Path:
        return self.data_dir / "profile_facts.yaml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
