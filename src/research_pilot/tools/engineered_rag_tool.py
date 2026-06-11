import os
import importlib.util
import json
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from research_pilot.config import settings
from research_pilot.core.evidence import EvidenceItem, EvidenceType
from research_pilot.core.observation import Observation
from research_pilot.core.tool import BaseTool, ToolSpec


def _get_rag_root() -> Path:
    if not settings.paper_rag_assistant_root:
        raise RuntimeError(
            "PAPER_RAG_ASSISTANT_ROOT is not set in .env. "
            "It should point to your paper-rag-assistant project root."
        )

    root = Path(settings.paper_rag_assistant_root).expanduser().resolve()

    if not root.exists():
        raise FileNotFoundError(f"paper-rag-assistant root does not exist: {root}")

    expected = root / "src" / "rag_engineered.py"
    if not expected.exists():
        raise FileNotFoundError(
            f"Cannot find rag_engineered.py at: {expected}\n"
            "Check PAPER_RAG_ASSISTANT_ROOT."
        )

    return root


def _load_module_from_file(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))

    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {file_path}")

    module = importlib.util.module_from_spec(spec)

    # Register module so relative runtime imports behave more predictably.
    sys.modules[module_name] = module

    spec.loader.exec_module(module)
    return module


def _prepare_rag_project() -> Path:
    """Prepare import path and environment for paper-rag-assistant."""

    root = _get_rag_root()
    src_dir = root / "src"

    # 1. Load paper-rag-assistant's own .env if it exists.
    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)

    # 2. Explicitly inject ResearchPilot settings into os.environ.
    # Old paper-rag-assistant code reads from os.getenv(...), not from our Pydantic settings.
    dashscope_key = settings.dashscope_api_key or settings.openai_api_key
    llm_base_url = settings.llm_base_url or settings.openai_base_url
    llm_model = settings.llm_model or settings.openai_model

    if dashscope_key:
        os.environ["DASHSCOPE_API_KEY"] = dashscope_key

    if llm_base_url:
        os.environ["LLM_BASE_URL"] = llm_base_url

    if llm_model:
        os.environ["LLM_MODEL"] = llm_model

    # 3. Make paper-rag-assistant/src importable.
    src_str = str(src_dir)
    if src_str in sys.path:
        sys.path.remove(src_str)

    sys.path.insert(0, src_str)

    return root


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _collect_researchpilot_pdfs(workspace: Path) -> list[Path]:
    paper_root = workspace / "documents" / "papers"
    index_path = paper_root / "download_index.json"

    pdf_paths: list[Path] = []

    index = _load_json(index_path)

    for item in index.values():
        path_text = item.get("path") or item.get("relative_path")

        if not path_text:
            continue

        path = Path(path_text)

        if not path.is_absolute():
            path = Path.cwd() / path

        path = path.resolve()

        if path.exists() and path.suffix.lower() == ".pdf":
            pdf_paths.append(path)

    if not pdf_paths and paper_root.exists():
        pdf_paths.extend(sorted(paper_root.rglob("*.pdf")))

    seen: set[str] = set()
    unique: list[Path] = []

    for path in pdf_paths:
        key = str(path.resolve()).lower()
        if key in seen:
            continue

        seen.add(key)
        unique.append(path)

    return unique


def _copy_pdfs_to_rag_project(local_pdfs: list[Path], rag_root: Path) -> list[dict[str, str]]:
    target_dir = rag_root / "data" / "papers"
    target_dir.mkdir(parents=True, exist_ok=True)

    copied: list[dict[str, str]] = []

    for pdf_path in local_pdfs:
        target_path = target_dir / pdf_path.name

        if not target_path.exists():
            shutil.copy2(pdf_path, target_path)

        copied.append(
            {
                "source": str(pdf_path),
                "target": str(target_path),
            }
        )

    return copied


@lru_cache(maxsize=1)
def _load_engineered_rag_class():
    rag_root = _prepare_rag_project()
    module_path = rag_root / "src" / "rag_engineered.py"
    module = _load_module_from_file("external_paper_rag_engineered", module_path)
    return module.EngineeredRAG


def _load_build_index_module():
    rag_root = _prepare_rag_project()
    module_path = rag_root / "src" / "build_index.py"
    return _load_module_from_file("external_paper_rag_build_index", module_path)


def _load_build_catalog_module():
    rag_root = _prepare_rag_project()
    module_path = rag_root / "src" / "build_paper_catalog.py"
    return _load_module_from_file("external_paper_rag_build_catalog", module_path)


class EngineeredRAGIndexTool(BaseTool):
    name = "engineered_rag_index"
    description = (
        "Sync ResearchPilot-downloaded PDFs into paper-rag-assistant and rebuild "
        "the engineered RAG chunk index and paper catalog."
    )

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "sync_downloaded_papers": "Whether to copy ResearchPilot downloaded PDFs into paper-rag-assistant/data/papers. Default true.",
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        sync_downloaded_papers = bool(tool_input.get("sync_downloaded_papers", True))

        try:
            rag_root = _prepare_rag_project()

            copied = []
            if sync_downloaded_papers:
                local_pdfs = _collect_researchpilot_pdfs(self.workspace)
                copied = _copy_pdfs_to_rag_project(local_pdfs, rag_root)

            build_index_module = _load_build_index_module()
            build_catalog_module = _load_build_catalog_module()

            build_index_module.build_index()
            build_catalog_module.build_catalog()

            # EngineeredRAG class is cached, but after rebuilding indexes we want
            # a fresh instance next time.
            _load_engineered_rag_class.cache_clear()

            content = (
                "Engineered RAG index rebuilt successfully.\n"
                f"paper-rag-assistant root: {rag_root}\n"
                f"Synced PDFs: {len(copied)}\n"
                f"Chunk index directory: {rag_root / 'chroma_db'}\n"
                f"Paper catalog directory: {rag_root / 'paper_catalog_db'}"
            )

            if state is not None:
                state.evidence_store.add(
                    EvidenceItem(
                        evidence_type=EvidenceType.PAPER,
                        source="engineered_rag_index",
                        content=content,
                        metadata={
                            "rag_root": str(rag_root),
                            "synced_pdfs": copied,
                        },
                    )
                )

            return Observation(
                success=True,
                content=content,
                metadata={
                    "rag_root": str(rag_root),
                    "synced_pdfs": copied,
                },
            )

        except Exception as exc:
            return Observation(
                success=False,
                content=(
                    "Failed to rebuild EngineeredRAG index.\n"
                    f"Error type: {type(exc).__name__}\n"
                    f"Error message: {exc}"
                ),
                error="EngineeredRAGIndexFailed",
            )


class EngineeredRAGSearchTool(BaseTool):
    name = "engineered_rag_search"
    description = (
        "Retrieve evidence chunks from the paper-rag-assistant EngineeredRAG backend."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "query": "Question or query for the engineered paper RAG system.",
                "paper_k": "Optional number of candidate papers.",
                "chunk_k": "Optional number of evidence chunks.",
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        query = tool_input.get("query", "")

        if not query:
            return Observation(
                success=False,
                content="Missing input: query",
                error="MissingQuery",
            )

        paper_k = tool_input.get("paper_k")
        chunk_k = tool_input.get("chunk_k")

        try:
            EngineeredRAG = _load_engineered_rag_class()
            rag = EngineeredRAG()

            docs, retrieval_info = rag.retrieve(
                query=query,
                paper_k=paper_k,
                chunk_k=chunk_k,
            )

            context = rag.format_context(docs)

            content = (
                "EngineeredRAG retrieved evidence chunks.\n\n"
                f"Query: {query}\n"
                f"Retrieval mode: {retrieval_info.get('mode')}\n\n"
                "Important downstream instruction:\n"
                "- The retrieved context below is already extracted text from indexed PDFs.\n"
                "- Do not call read_file on the returned source filenames.\n"
                "- If more evidence is needed, call engineered_rag_search again with a refined query.\n\n"
                "- For final question answering, call write_evidence_answer using this retrieved evidence.\n\n"
                f"Candidate papers:\n"
            )

            evidence_blocks = []

            for i, doc in enumerate(docs, start=1):
                evidence_blocks.append(
                    {
                        "source_id": i,
                        "file": doc.metadata.get("source", "unknown"),
                        "page": doc.metadata.get("page", "unknown"),
                        "chunk_id": doc.metadata.get("chunk_id", "unknown"),
                        "chunk_type": doc.metadata.get("chunk_type", "unknown"),
                        "vector_score": doc.metadata.get("vector_score", "unknown"),
                        "bm25_score": doc.metadata.get("bm25_score", "unknown"),
                        "reranker_score": doc.metadata.get("reranker_score", "unknown"),
                        "content": doc.page_content,
                    }
                )

            for item in retrieval_info.get("candidate_papers", []):
                content += (
                    f"- {item.get('title')} | "
                    f"source={item.get('source')} | "
                    f"score={item.get('score')}\n"
                )

            content += "\nRetrieved context:\n"
            content += context

            metadata = {
                "query": query,
                "backend": "paper-rag-assistant EngineeredRAG",
                "retrieval_info": retrieval_info,
                "num_docs": len(docs),
                "evidence_blocks": evidence_blocks,
                "sources": [
                    {
                        "source": doc.metadata.get("source"),
                        "page": doc.metadata.get("page"),
                        "chunk_id": doc.metadata.get("chunk_id"),
                        "chunk_type": doc.metadata.get("chunk_type"),
                        "reranker_score": doc.metadata.get("reranker_score"),
                        "vector_score": doc.metadata.get("vector_score"),
                        "bm25_score": doc.metadata.get("bm25_score"),
                    }
                    for doc in docs
                ],
            }

            if state is not None:
                state.evidence_store.add(
                    EvidenceItem(
                        evidence_type=EvidenceType.PAPER,
                        source=f"engineered_rag_search:{query}",
                        content=content,
                        metadata=metadata,
                    )
                )

            return Observation(
                success=True,
                content=content,
                metadata=metadata,
            )

        except Exception as exc:
            return Observation(
                success=False,
                content=(
                    "Failed to search EngineeredRAG backend.\n"
                    f"Error type: {type(exc).__name__}\n"
                    f"Error message: {exc}\n\n"
                    "Possible fixes:\n"
                    "1. Check PAPER_RAG_ASSISTANT_ROOT.\n"
                    "2. Install paper-rag-assistant requirements.\n"
                    "3. Run engineered_rag_index first.\n"
                    "4. Check paper-rag-assistant/.env for DASHSCOPE_API_KEY, LLM_BASE_URL, and LLM_MODEL."
                ),
                error="EngineeredRAGSearchFailed",
            )


class EngineeredRAGAnswerTool(BaseTool):
    name = "engineered_rag_answer"
    description = (
        "Use paper-rag-assistant EngineeredRAG to retrieve evidence and generate "
        "a source-grounded answer."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "question": "Question for the engineered paper RAG system.",
                "paper_k": "Optional number of candidate papers.",
                "chunk_k": "Optional number of evidence chunks.",
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        question = tool_input.get("question", "")

        if not question:
            return Observation(
                success=False,
                content="Missing input: question",
                error="MissingQuestion",
            )

        paper_k = tool_input.get("paper_k")
        chunk_k = tool_input.get("chunk_k")

        try:
            EngineeredRAG = _load_engineered_rag_class()
            rag = EngineeredRAG()

            answer, docs, retrieval_info = rag.answer_question(
                question=question,
                paper_k=paper_k,
                chunk_k=chunk_k,
                show_debug=False,
            )

            content = (
                "EngineeredRAG answer:\n\n"
                f"{answer}\n\n"
                "Retrieved sources:\n"
            )

            for i, doc in enumerate(docs, start=1):
                content += (
                    f"[Source {i}] "
                    f"{doc.metadata.get('source')}, "
                    f"page={doc.metadata.get('page')}, "
                    f"chunk={doc.metadata.get('chunk_id')}, "
                    f"reranker_score={doc.metadata.get('reranker_score')}\n"
                )

            metadata = {
                "question": question,
                "backend": "paper-rag-assistant EngineeredRAG",
                "retrieval_info": retrieval_info,
                "num_docs": len(docs),
            }

            if state is not None:
                state.evidence_store.add(
                    EvidenceItem(
                        evidence_type=EvidenceType.PAPER,
                        source=f"engineered_rag_answer:{question}",
                        content=content,
                        metadata=metadata,
                    )
                )

            return Observation(
                success=True,
                content=content,
                metadata=metadata,
            )

        except Exception as exc:
            return Observation(
                success=False,
                content=(
                    "Failed to generate EngineeredRAG answer.\n"
                    f"Error type: {type(exc).__name__}\n"
                    f"Error message: {exc}"
                ),
                error="EngineeredRAGAnswerFailed",
            )