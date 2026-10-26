from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://outreach:outreach@localhost:5432/outreach"
    api_token: SecretStr = SecretStr("")
    data_dir: Path = Path("data")
    api_url: str = "http://127.0.0.1:8000"
    sending_enabled: bool = False
    dry_run: bool = True
    test_recipient: str = ""
    allow_recruiter_delivery: bool = False
    sender_email: str = ""
    sender_name: str = ""
    daily_send_limit: int = Field(default=5, ge=1, le=50)
    contact_cooldown_days: int = Field(default=30, ge=1)
    company_cooldown_days: int = Field(default=7, ge=1)
    timezone: str = "Asia/Kolkata"
    schedule_hour: int = Field(default=9, ge=0, le=23)
    source_boards: list[dict] = []
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    embedding_model: str = ""
    semantic_threshold: float = Field(default=0.25, ge=-1, le=1)
    llm_calls_per_run: int = Field(default=10, ge=0, le=100)
    credential_key: SecretStr = SecretStr("")
    oauth_client_file: Path = Path("data/credentials.json")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo

        ZoneInfo(value)
        return value


def settings() -> Settings:
    return Settings()
