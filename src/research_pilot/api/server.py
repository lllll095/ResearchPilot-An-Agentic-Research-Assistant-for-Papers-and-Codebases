from functools import lru_cache
from typing import Any

import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from research_pilot.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    PaperResearchRequest,
    PaperResearchResponse,
)

# 第一版先复用 CLI 里已经稳定的 builder。
# 后续如果想进一步解耦，可以把这些 builder 移到 runtime/builders.py。
from research_pilot.cli import (
    build_multiagent_graph_workflow_runner,
    build_paper_workflow_runner,
)


app = FastAPI(
    title="ResearchPilot API",
    description=(
        "FastAPI service layer for ResearchPilot. "
        "Provides chat and adaptive paper research endpoints."
    ),
    version="0.1.0",
)


@lru_cache(maxsize=1)
def get_llm_client():
    """Build and cache an LLM client for direct streaming."""
    from research_pilot.core.llm_client import OpenAICompatibleLLMClient
    return OpenAICompatibleLLMClient.from_settings()


@lru_cache(maxsize=1)
def get_multiagent_runner():
    """Build and cache graph-based multi-agent runner.

    The runner can be expensive to initialize because it registers tools,
    initializes workflows, and may load LLM/RAG-related components.
    """

    return build_multiagent_graph_workflow_runner(verbose=False)


@lru_cache(maxsize=1)
def get_paper_runner():
    """Build and cache paper workflow runner."""

    return build_paper_workflow_runner(verbose=False)


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Return JSON-friendly metadata.

    Some internal objects may not be JSON serializable. This function keeps
    the API robust by converting unsafe values to strings.
    """

    if not metadata:
        return {}

    safe: dict[str, Any] = {}

    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, (list, dict)):
            safe[key] = value
        else:
            safe[key] = str(value)

    return safe


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Health check endpoint."""

    return HealthResponse()


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Run ResearchPilot chat through graph-based multi-agent workflow.

    This endpoint is intentionally minimal. It does not yet support streaming,
    persistent sessions, or background tasks. Those can be added later.
    """

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    try:
        if request.use_multi_agent:
            runner = get_multiagent_runner()

            state = runner.answer(
                user_request=request.message,
                session=None,
            )

            return ChatResponse(
                answer=state.final_answer or "",
                mode="graph-multi-agent",
                metadata=_safe_metadata(state.metadata),
            )

        raise HTTPException(
            status_code=400,
            detail="Only graph-based multi-agent chat is supported in API Phase 1A.",
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc



@app.post("/chat/direct")
def chat_direct(request: ChatRequest) -> StreamingResponse:
    """Direct LLM chat with streaming response via Server-Sent Events.

    This endpoint bypasses the multi-agent workflow and calls the LLM directly,
    streaming each token as a SSE event. Unlike /chat, this endpoint does not
    use tools, workflows, or agent orchestration.

    SSE event format:
        data: {"token": "hello"}
        data: {"token": " world"}
        data: {"done": true}

    Useful for:
    - Testing LLM connectivity.
    - Building streaming chat UIs.
    - Demonstrating the streaming capability.
    """

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    llm_client = get_llm_client()
    messages = [{"role": "user", "content": request.message}]

    def event_stream():
        for token in llm_client.stream(messages):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.post("/paper-research", response_model=PaperResearchResponse)
def paper_research(request: PaperResearchRequest) -> PaperResearchResponse:
    """Run adaptive paper research workflow.

    This directly calls PaperWorkflowRunner.paper_research.
    It is useful for demonstrating the paper research service without going
    through the full multi-agent graph.
    """

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question cannot be empty")

    try:
        runner = get_paper_runner()

        state = runner.paper_research(
            question=request.question,
            max_papers=request.max_papers,
            min_sources=request.min_sources,
            force_download=request.force_download,
            save_report=request.save_report,
        )

        return PaperResearchResponse(
            answer=state.final_answer or "",
            metadata=_safe_metadata(state.metadata),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc