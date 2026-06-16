from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "research-pilot-api"


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message.")
    use_multi_agent: bool = Field(
        default=True,
        description="Whether to use graph-based multi-agent workflow.",
    )
    save_trace_report: bool = Field(
        default=False,
        description="Whether to save a multi-agent trace report.",
    )


class ChatResponse(BaseModel):
    answer: str
    mode: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaperResearchRequest(BaseModel):
    question: str = Field(..., description="Paper research question.")
    max_papers: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of papers to download.",
    )
    min_sources: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Minimum number of evidence sources.",
    )
    force_download: bool = Field(
        default=False,
        description="Whether to force paper download before answering.",
    )
    save_report: bool = Field(
        default=True,
        description="Whether to save a generated report.",
    )


class PaperResearchResponse(BaseModel):
    answer: str
    metadata: dict[str, Any] = Field(default_factory=dict)