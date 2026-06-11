import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from research_pilot.config import settings


def _json_safe(obj: Any) -> Any:
    """Convert objects to JSON-safe values."""

    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]

    return str(obj)


def _get_rag_root() -> Path:
    if not settings.paper_rag_assistant_root:
        raise RuntimeError("PAPER_RAG_ASSISTANT_ROOT is not set.")

    root = Path(settings.paper_rag_assistant_root).expanduser().resolve()

    if not root.exists():
        raise FileNotFoundError(f"paper-rag-assistant root does not exist: {root}")

    expected = root / "src" / "rag_engineered.py"
    if not expected.exists():
        raise FileNotFoundError(f"Cannot find rag_engineered.py at: {expected}")

    return root


def _load_module_from_file(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))

    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _prepare_rag_project() -> Path:
    """Prepare paper-rag-assistant environment inside this subprocess."""

    root = _get_rag_root()
    src_dir = root / "src"

    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)

    dashscope_key = settings.dashscope_api_key or settings.openai_api_key
    llm_base_url = settings.llm_base_url or settings.openai_base_url
    llm_model = settings.llm_model or settings.openai_model

    if dashscope_key:
        os.environ["DASHSCOPE_API_KEY"] = dashscope_key

    if llm_base_url:
        os.environ["LLM_BASE_URL"] = llm_base_url

    if llm_model:
        os.environ["LLM_MODEL"] = llm_model

    src_str = str(src_dir)
    if src_str in sys.path:
        sys.path.remove(src_str)

    sys.path.insert(0, src_str)

    return root


def _load_engineered_rag_class():
    rag_root = _prepare_rag_project()
    module_path = rag_root / "src" / "rag_engineered.py"
    module = _load_module_from_file("external_paper_rag_engineered_worker", module_path)
    return module.EngineeredRAG


def _run_index() -> dict[str, Any]:
    rag_root = _prepare_rag_project()

    build_index_module = _load_module_from_file(
        "external_paper_rag_build_index_worker",
        rag_root / "src" / "build_index.py",
    )

    build_catalog_module = _load_module_from_file(
        "external_paper_rag_build_catalog_worker",
        rag_root / "src" / "build_paper_catalog.py",
    )

    build_index_module.build_index()
    build_catalog_module.build_catalog()

    return {
        "success": True,
        "content": (
            "Engineered RAG index rebuilt successfully.\n"
            f"paper-rag-assistant root: {rag_root}\n"
            f"Chunk index directory: {rag_root / 'chroma_db'}\n"
            f"Paper catalog directory: {rag_root / 'paper_catalog_db'}"
        ),
        "metadata": {
            "rag_root": str(rag_root),
            "chroma_db": str(rag_root / "chroma_db"),
            "paper_catalog_db": str(rag_root / "paper_catalog_db"),
        },
    }


def _make_evidence_blocks(docs: list[Any]) -> list[dict[str, Any]]:
    blocks = []

    for i, doc in enumerate(docs, start=1):
        blocks.append(
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

    return blocks


def _run_search(payload: dict[str, Any]) -> dict[str, Any]:
    query = payload.get("query", "")
    paper_k = payload.get("paper_k")
    chunk_k = payload.get("chunk_k")

    if not query:
        raise ValueError("Missing query.")

    EngineeredRAG = _load_engineered_rag_class()
    rag = EngineeredRAG()

    docs, retrieval_info = rag.retrieve(
        query=query,
        paper_k=paper_k,
        chunk_k=chunk_k,
    )

    context = rag.format_context(docs)
    evidence_blocks = _make_evidence_blocks(docs)

    content = (
        "EngineeredRAG retrieved evidence chunks.\n\n"
        f"Query: {query}\n"
        f"Retrieval mode: {retrieval_info.get('mode')}\n\n"
        "Important downstream instruction:\n"
        "- The retrieved context below is already extracted text from indexed PDFs.\n"
        "- Do not call read_file on the returned source filenames.\n"
        "- If more evidence is needed, call engineered_rag_search again with a refined query.\n"
        "- For final question answering, call write_evidence_answer using this retrieved evidence.\n\n"
        "Candidate papers:\n"
    )

    for item in retrieval_info.get("candidate_papers", []):
        content += (
            f"- {item.get('title')} | "
            f"source={item.get('source')} | "
            f"score={item.get('score')}\n"
        )

    content += "\nRetrieved context:\n"
    content += context

    return {
        "success": True,
        "content": content,
        "metadata": {
            "query": query,
            "backend": "paper-rag-assistant EngineeredRAG subprocess",
            "retrieval_info": _json_safe(retrieval_info),
            "num_docs": len(docs),
            "evidence_blocks": _json_safe(evidence_blocks),
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
        },
    }


def _run_answer(payload: dict[str, Any]) -> dict[str, Any]:
    question = payload.get("question", "")
    paper_k = payload.get("paper_k")
    chunk_k = payload.get("chunk_k")

    if not question:
        raise ValueError("Missing question.")

    EngineeredRAG = _load_engineered_rag_class()
    rag = EngineeredRAG()

    answer, docs, retrieval_info = rag.answer_question(
        question=question,
        paper_k=paper_k,
        chunk_k=chunk_k,
        show_debug=False,
    )

    content = "EngineeredRAG answer:\n\n"
    content += answer
    content += "\n\nRetrieved sources:\n"

    for i, doc in enumerate(docs, start=1):
        content += (
            f"[Source {i}] "
            f"{doc.metadata.get('source')}, "
            f"page={doc.metadata.get('page')}, "
            f"chunk={doc.metadata.get('chunk_id')}, "
            f"reranker_score={doc.metadata.get('reranker_score')}\n"
        )

    return {
        "success": True,
        "content": content,
        "metadata": {
            "question": question,
            "backend": "paper-rag-assistant EngineeredRAG subprocess",
            "retrieval_info": _json_safe(retrieval_info),
            "num_docs": len(docs),
            "evidence_blocks": _json_safe(_make_evidence_blocks(docs)),
        },
    }


def _run_command(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    if command == "index":
        return _run_index()

    if command == "search":
        return _run_search(payload)

    if command == "answer":
        return _run_answer(payload)

    raise ValueError(f"Unknown command: {command}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    try:
        request = json.loads(input_path.read_text(encoding="utf-8"))
        command = request["command"]
        payload = request.get("payload", {})

        result = _run_command(command=command, payload=payload)

    except Exception as exc:
        result = {
            "success": False,
            "content": (
                "EngineeredRAG worker failed.\n"
                f"Error type: {type(exc).__name__}\n"
                f"Error message: {exc}"
            ),
            "error": "EngineeredRAGWorkerFailed",
            "metadata": {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_json_safe(result), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if not result.get("success"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()