from pathlib import Path
from typing import Any

from research_pilot.config import settings
from research_pilot.core.evidence import EvidenceItem, EvidenceType
from research_pilot.core.observation import Observation
from research_pilot.core.tool import BaseTool


CODE_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".env.example",
}

IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "workspace",
    "dist",
    "build",
    "helloagents-chapter14",
    "paper-rag-assistant",
    "paper-rag-week1",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _safe_resolve_repo_path(path: str | None = None) -> Path:
    root = _project_root()

    if not path:
        return root

    candidate = Path(path)

    if not candidate.is_absolute():
        candidate = root / candidate

    candidate = candidate.resolve()

    if root not in candidate.parents and candidate != root:
        raise ValueError(f"Path is outside project root: {candidate}")

    return candidate


def _should_ignore(path: Path) -> bool:
    parts = set(path.parts)

    for ignored in IGNORED_DIRS:
        if ignored in parts:
            return True

    if path.name.endswith(".egg-info"):
        return True

    return False


def _is_text_code_file(path: Path) -> bool:
    if _should_ignore(path):
        return False

    if not path.is_file():
        return False

    if path.name == ".env":
        return False

    if path.suffix in CODE_EXTENSIONS:
        return True

    if path.name.endswith(".env.example"):
        return True

    return False


def _iter_code_files(root: Path) -> list[Path]:
    files: list[Path] = []

    for path in root.rglob("*"):
        if _should_ignore(path):
            continue

        if _is_text_code_file(path):
            files.append(path)

    return sorted(files)


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


class CodeMapTool(BaseTool):
    """Create a lightweight map of the current codebase."""

    name = "code_map"
    description = (
        "Scan the project codebase and return a compact file tree grouped by directory."
    )

    def run(self, tool_input: dict, state=None) -> Observation:
        path = tool_input.get("path")
        max_files = int(tool_input.get("max_files", 200))

        try:
            root = _safe_resolve_repo_path(path)
            files = _iter_code_files(root)[:max_files]

            project_root = _project_root()

            grouped: dict[str, list[str]] = {}

            for file_path in files:
                rel = file_path.relative_to(project_root)
                directory = str(rel.parent)
                grouped.setdefault(directory, []).append(rel.name)

            lines = [
                "# Codebase Map",
                "",
                f"Root: {root}",
                f"Files shown: {len(files)}",
                "",
            ]

            for directory, names in sorted(grouped.items()):
                lines.append(f"## {directory}")
                for name in names:
                    lines.append(f"- {name}")
                lines.append("")

            content = "\n".join(lines)

            if state is not None:
                state.evidence_store.add(
                    EvidenceItem(
                        evidence_type=EvidenceType.CODE,
                        source="code_map",
                        content=content,
                        metadata={
                            "root": str(root),
                            "num_files": len(files),
                        },
                    )
                )

            return Observation(
                success=True,
                content=content,
                metadata={
                    "root": str(root),
                    "num_files": len(files),
                },
            )

        except Exception as exc:
            return Observation(
                success=False,
                content=(
                    "Failed to create codebase map.\n"
                    f"Error type: {type(exc).__name__}\n"
                    f"Error message: {exc}"
                ),
                error="CodeMapFailed",
            )




def _search_with_rg(
    query: str,
    root: Path,
    max_results: int = 30,
    context_lines: int = 2,
) -> list[dict[str, Any]] | None:
    """Fast code search using ripgrep (rg).

    Returns a list of match dicts, or None if rg is not available.
    Falls back to Python-based search when rg is unavailable.
    """
    import json as _json
    import subprocess as _sp

    try:
        result = _sp.run(
            ["rg", "-n", "--json", "-C", str(context_lines), "-m", str(max_results), query, str(root)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode not in (0, 1):
            return None
        if not result.stdout.strip():
            return []

        matches: list[dict[str, Any]] = []
        for line in result.stdout.strip().split("\n"):
            try:
                data = _json.loads(line)
                if data.get("type") == "match":
                    md = data.get("data", {})
                    fpath = md.get("path", {}).get("text", "")
                    matches.append({
                        "file": fpath,
                        "line_number": md.get("line_number", 0),
                        "line": md.get("lines", {}).get("text", "").rstrip("\n"),
                    })
            except _json.JSONDecodeError:
                continue
        return matches[:max_results]
    except (FileNotFoundError, _sp.TimeoutExpired, OSError):
        return None


class CodeSearchTool(BaseTool):
    """Search code files using simple keyword matching."""

    name = "code_search"
    description = (
        "Search project code files for keywords and return matching lines with file paths and line numbers."
    )

    def run(self, tool_input: dict, state=None) -> Observation:
        query = tool_input.get("query", "")
        path = tool_input.get("path", "src/research_pilot")
        max_results = int(tool_input.get("max_results", 30))
        context_lines = int(tool_input.get("context_lines", 2))

        if not query:
            return Observation(
                success=False,
                content="Missing input: query",
                error="MissingQuery",
            )

        try:
            root = _safe_resolve_repo_path(path)
            project_root = _project_root()

            # Try ripgrep first for fast search
            matches = _search_with_rg(query, root, max_results, context_lines)

            # Fall back to Python-based search
            if matches is None:
                keywords = self._extract_keywords(query)
                files = _iter_code_files(root)
                matches = []

            for file_path in files:
                text = _read_text_file(file_path)
                lines = text.splitlines()

                for idx, line in enumerate(lines):
                    line_lower = line.lower()

                    if self._line_matches(line_lower=line_lower, keywords=keywords):
                        start = max(0, idx - context_lines)
                        end = min(len(lines), idx + context_lines + 1)

                        snippet_lines = []
                        for line_no in range(start, end):
                            snippet_lines.append(
                                f"{line_no + 1}: {lines[line_no]}"
                            )

                        rel_file = str(file_path.relative_to(project_root))

                        match = {
                            "file": rel_file,
                            "line": idx + 1,
                            "matched_line": line.strip(),
                            "snippet": "\n".join(snippet_lines),
                        }

                        match["score"] = self._score_match(
                            query=query,
                            keywords=keywords,
                            match=match,
                        )

                        matches.append(match)

            # Sort after collecting all matches.
            matches = sorted(
                matches,
                key=lambda item: item.get("score", 0),
                reverse=True,
            )[:max_results]

            content = self._render_matches(query, keywords, matches)

            if state is not None:
                state.evidence_store.add(
                    EvidenceItem(
                        evidence_type=EvidenceType.CODE,
                        source=f"code_search:{query}",
                        content=content,
                        metadata={
                            "query": query,
                            "keywords": keywords,
                            "num_matches": len(matches),
                            "matches": matches,
                        },
                    )
                )

            return Observation(
                success=True,
                content=content,
                metadata={
                    "query": query,
                    "keywords": keywords,
                    "num_matches": len(matches),
                    "matches": matches,
                },
            )

        except Exception as exc:
            return Observation(
                success=False,
                content=(
                    "Failed to search codebase.\n"
                    f"Error type: {type(exc).__name__}\n"
                    f"Error message: {exc}"
                ),
                error="CodeSearchFailed",
            )
        
    @staticmethod
    def _line_matches(line_lower: str, keywords: list[str]) -> bool:
        """Return whether a line matches the search keywords."""

        if not keywords:
            return False

        # If there is only one keyword, one hit is enough.
        if len(keywords) == 1:
            return keywords[0] in line_lower

        # For multiple keywords, require the rare/specific one and at least
        # one additional keyword when possible.
        hits = [keyword for keyword in keywords if keyword in line_lower]

        return len(hits) >= 1


    @staticmethod
    def _score_match(
        query: str,
        keywords: list[str],
        match: dict[str, Any],
    ) -> int:
        """Score code search matches so real source files rank before docs."""

        file = str(match.get("file", "")).replace("\\", "/").lower()
        line = str(match.get("matched_line", "")).lower()
        query_lower = query.lower().strip()

        score = 0

        # Prefer actual project source code.
        if file.startswith("src/research_pilot/"):
            score += 50

        # Prefer core implementation for Agent Harness questions.
        if "/core/" in file:
            score += 20

        # Prefer Python files.
        if file.endswith(".py"):
            score += 20

        # Penalize docs for implementation questions.
        if file.startswith("docs/"):
            score -= 30

        # Penalize external or reference projects.
        if "helloagents-chapter14/" in file:
            score -= 50
        if "paper-rag-assistant/" in file:
            score -= 50

        # Prefer filename-level matches.
        for keyword in keywords:
            normalized_keyword = keyword.replace("_", "").lower()
            normalized_file = file.replace("_", "").lower()

            if normalized_keyword in normalized_file:
                score += 30

        # Prefer exact query phrase when present.
        if query_lower and query_lower in line:
            score += 30

        # Prefer class/function definitions.
        if line.startswith("class "):
            score += 20
        if line.startswith("def "):
            score += 15

        # Reward keyword hits.
        for keyword in keywords:
            if keyword in line:
                score += 10

        return score

    @staticmethod
    def _extract_keywords(query: str) -> list[str]:
        raw_tokens = (
            query.replace("_", " ")
            .replace("-", " ")
            .replace(".", " ")
            .replace("/", " ")
            .split()
        )

        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "what",
            "how",
            "why",
            "where",
            "when",
            "does",
            "do",
            "to",
            "of",
            "in",
            "and",
            "or",
            "for",
            "with",
            "this",
            "that",
            "这个",
            "那个",
            "怎么",
            "如何",
            "为什么",
            "是什么",
            "class",
            "def",
            "function",
            "method",
            "implementation",
            "implemented",
            "where",
            "find",
        }

        keywords = []

        for token in raw_tokens:
            token = token.strip().lower()

            if len(token) < 3:
                continue

            if token in stopwords:
                continue

            keywords.append(token)

        if not keywords:
            keywords = [query.lower()]

        return list(dict.fromkeys(keywords))

    @staticmethod
    def _render_matches(
        query: str,
        keywords: list[str],
        matches: list[dict[str, Any]],
    ) -> str:
        lines = [
            "# Code Search Results",
            "",
            f"Query: {query}",
            f"Keywords: {', '.join(keywords)}",
            f"Matches: {len(matches)}",
            "",
        ]

        if not matches:
            lines.append("No matches found.")
            return "\n".join(lines)

        for i, match in enumerate(matches, start=1):
            lines.extend(
                [
                    f"## Match {i}",
                    "",
                    f"File: {match['file']}",
                    f"Line: {match['line']}",
                    "",
                    "```text",
                    match["snippet"],
                    "```",
                    "",
                ]
            )

        return "\n".join(lines)


class CodeReadTool(BaseTool):
    """Read a code file with line numbers."""

    name = "code_read"
    description = (
        "Read a code or text file with line numbers. Useful for codebase understanding."
    )

    def run(self, tool_input: dict, state=None) -> Observation:
        path = tool_input.get("path", "")
        start_line = int(tool_input.get("start_line", 1))

        # Support both:
        #   {"start_line": 10, "max_lines": 80}
        # and:
        #   {"start_line": 10, "end_line": 50}
        if "end_line" in tool_input and "max_lines" not in tool_input:
            end_line = int(tool_input.get("end_line"))
            max_lines = max(1, end_line - start_line + 1)
        else:
            max_lines = int(tool_input.get("max_lines", 120))

        if not path:
            return Observation(
                success=False,
                content="Missing input: path",
                error="MissingPath",
            )

        try:
            file_path = _safe_resolve_repo_path(path)

            if not file_path.exists():
                return Observation(
                    success=False,
                    content=f"File not found: {file_path}",
                    error="FileNotFound",
                )

            if not _is_text_code_file(file_path):
                return Observation(
                    success=False,
                    content=f"Not a supported text/code file: {file_path}",
                    error="UnsupportedFile",
                )

            text = _read_text_file(file_path)
            lines = text.splitlines()

            start_idx = max(0, start_line - 1)
            end_idx = min(len(lines), start_idx + max_lines)

            numbered = []
            for idx in range(start_idx, end_idx):
                numbered.append(f"{idx + 1}: {lines[idx]}")

            project_root = _project_root()
            rel = file_path.relative_to(project_root)

            content = (
                f"# Code File: {rel}\n\n"
                f"Lines: {start_idx + 1}-{end_idx} / {len(lines)}\n\n"
                "```text\n"
                + "\n".join(numbered)
                + "\n```"
            )

            if state is not None:
                state.evidence_store.add(
                    EvidenceItem(
                        evidence_type=EvidenceType.CODE,
                        source=f"code_read:{rel}",
                        content=content,
                        metadata={
                            "file": str(rel),
                            "start_line": start_idx + 1,
                            "end_line": end_idx,
                            "num_lines": len(lines),
                        },
                    )
                )

            return Observation(
                success=True,
                content=content,
                metadata={
                    "file": str(rel),
                    "start_line": start_idx + 1,
                    "end_line": end_idx,
                    "num_lines": len(lines),
                },
            )

        except Exception as exc:
            return Observation(
                success=False,
                content=(
                    "Failed to read code file.\n"
                    f"Error type: {type(exc).__name__}\n"
                    f"Error message: {exc}"
                ),
                error="CodeReadFailed",
            )