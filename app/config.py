from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    database_url: str = Field(alias="DATABASE_URL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    operator_id: str = Field(alias="OPERATOR_ID")

    openai_model: str = Field(default="gpt-5", alias="OPENAI_MODEL")
    openai_prompt_version: str = Field(default="v1", alias="OPENAI_PROMPT_VERSION")
    use_mock_ai: bool = Field(default=False, alias="USE_MOCK_AI")
    ai_enabled: bool = Field(default=False, alias="AI_ENABLED")

    artifact_root: Path = Field(default=Path("./data/artifacts"), alias="ARTIFACT_ROOT")
    ingest_root: Path = Field(default=Path("./__Reference__"), alias="INGEST_ROOT")
    worker_poll_seconds: int = Field(default=2, alias="WORKER_POLL_SECONDS")
    max_job_attempts: int = Field(default=3, alias="MAX_JOB_ATTEMPTS")
    max_source_chars: int = Field(default=250000, alias="MAX_SOURCE_CHARS")
    max_passages_per_source: int = Field(default=25, alias="MAX_PASSAGES_PER_SOURCE")
    max_register_fingerprint_chars: int = Field(default=120000, alias="MAX_REGISTER_FINGERPRINT_CHARS")
    parser_timeout_seconds: int = Field(default=30, alias="PARSER_TIMEOUT_SECONDS")

    @model_validator(mode="after")
    def validate_required_runtime(self) -> "Settings":
        if not self.database_url.strip():
            raise ValueError("DATABASE_URL is required")
        if not self.operator_id.strip():
            raise ValueError("OPERATOR_ID is required")
        if (not self.use_mock_ai) and self.ai_enabled and (not self.openai_api_key.strip()):
            raise ValueError("OPENAI_API_KEY is required when AI is enabled")
        if self.max_job_attempts < 1:
            raise ValueError("MAX_JOB_ATTEMPTS must be >= 1")
        if self.worker_poll_seconds < 1:
            raise ValueError("WORKER_POLL_SECONDS must be >= 1")
        if self.max_source_chars < 2000:
            raise ValueError("MAX_SOURCE_CHARS must be >= 2000")
        if self.max_passages_per_source < 1:
            raise ValueError("MAX_PASSAGES_PER_SOURCE must be >= 1")
        if self.max_register_fingerprint_chars < 2000:
            raise ValueError("MAX_REGISTER_FINGERPRINT_CHARS must be >= 2000")
        if self.parser_timeout_seconds < 1:
            raise ValueError("PARSER_TIMEOUT_SECONDS must be >= 1")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.artifact_root.mkdir(parents=True, exist_ok=True)
    return settings
