from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global settings loaded from environment variables."""

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    dashscope_api_key: str | None = Field(default=None, alias="DASHSCOPE_API_KEY")
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    llm_model: str | None = Field(default=None, alias="LLM_MODEL")

    workspace: Path = Field(default=Path("workspace"), alias="RESEARCH_PILOT_WORKSPACE")

    # Search configs.
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")
    web_search_backend: str = Field(default="mock", alias="WEB_SEARCH_BACKEND")

    # Paper download configs.
    max_paper_downloads: int = Field(default=3, alias="MAX_PAPER_DOWNLOADS")

    paper_rag_assistant_root: str | None = Field(
        default=None,
        alias="PAPER_RAG_ASSISTANT_ROOT",
    )

    # Future Paper RAG integration configs.
    paper_rag_project_root: str | None = Field(default=None, alias="PAPER_RAG_PROJECT_ROOT")
    paper_rag_engine_relative_path: str | None = Field(
        default=None,
        alias="PAPER_RAG_ENGINE_RELATIVE_PATH",
    )
    paper_rag_engine_class: str | None = Field(default=None, alias="PAPER_RAG_ENGINE_CLASS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()