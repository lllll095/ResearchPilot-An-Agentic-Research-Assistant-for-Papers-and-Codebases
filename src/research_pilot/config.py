from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global settings loaded from environment variables."""

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    workspace: Path = Field(default=Path("workspace"), alias="RESEARCH_PILOT_WORKSPACE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra="ignore"


settings = Settings()
