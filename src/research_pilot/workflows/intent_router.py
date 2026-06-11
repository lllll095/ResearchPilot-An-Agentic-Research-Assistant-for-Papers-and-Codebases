from enum import Enum
from pydantic import BaseModel


class IntentType(str, Enum):
    PAPER_ANSWER = "paper_answer"
    PAPER_COLLECT = "paper_collect"
    PAPER_RESEARCH = "paper_research"
    GENERAL_AGENT_RUN = "general_agent_run"


class RoutedIntent(BaseModel):
    intent_type: IntentType
    reason: str
    max_papers: int = 3
    save_report: bool = False
    force_download: bool = False


class IntentRouter:
    """A lightweight deterministic intent router.

    This router maps natural language user requests to stable workflows.
    It is intentionally simple and transparent.
    """

    def route(self, user_input: str) -> RoutedIntent:
        text = user_input.lower()

        wants_download = any(
            keyword in text
            for keyword in [
                "download",
                "下载",
                "collect papers",
                "find papers",
                "search papers",
                "arxiv papers",
                "相关论文",
                "下载论文",
                "搜索论文",
            ]
        )

        wants_report = any(
            keyword in text
            for keyword in [
                "report",
                "write a report",
                "summary report",
                "研究报告",
                "总结报告",
                "写报告",
            ]
        )

        mentions_papers = any(
            keyword in text
            for keyword in [
                "paper",
                "papers",
                "indexed papers",
                "local papers",
                "论文",
                "文献",
                "本地库",
                "indexed",
            ]
        )

        asks_question = any(
            keyword in text
            for keyword in [
                "what",
                "why",
                "how",
                "explain",
                "compare",
                "summarize",
                "是什么",
                "为什么",
                "怎么",
                "解释",
                "比较",
                "总结",
            ]
        )

        max_papers = self._extract_max_papers(text)

        if wants_download and not asks_question:
            return RoutedIntent(
                intent_type=IntentType.PAPER_COLLECT,
                reason="The user asks to search/download papers.",
                max_papers=max_papers,
                save_report=False,
                force_download=True,
            )

        if wants_download and asks_question:
            return RoutedIntent(
                intent_type=IntentType.PAPER_RESEARCH,
                reason="The user asks a research question and also asks to download papers.",
                max_papers=max_papers,
                save_report=wants_report,
                force_download=True,
            )

        if wants_report:
            return RoutedIntent(
                intent_type=IntentType.PAPER_RESEARCH,
                reason="The user asks for a research report.",
                max_papers=max_papers,
                save_report=True,
                force_download=False,
            )

        if mentions_papers or asks_question:
            return RoutedIntent(
                intent_type=IntentType.PAPER_ANSWER,
                reason="The user asks a question that can be answered from indexed papers.",
                max_papers=max_papers,
                save_report=False,
                force_download=False,
            )

        return RoutedIntent(
            intent_type=IntentType.GENERAL_AGENT_RUN,
            reason="No stable paper workflow matched; fall back to general agent run.",
            max_papers=max_papers,
            save_report=False,
            force_download=False,
        )

    @staticmethod
    def _extract_max_papers(text: str) -> int:
        for n in range(1, 11):
            if f"{n} paper" in text or f"{n} papers" in text or f"{n} 篇" in text:
                return n

        return 3