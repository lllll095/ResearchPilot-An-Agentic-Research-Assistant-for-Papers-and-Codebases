# src/research_pilot/multiagent/subagents/paper_subagent.py

from research_pilot.core.state import AgentState
from research_pilot.multiagent.base_subagent import (
    BaseSubAgent,
    SubAgentInput,
    SubAgentOutput,
)
from research_pilot.workflows.paper_workflows import PaperWorkflowRunner


class PaperSubAgent(BaseSubAgent):
    """Paper subagent with adaptive research behavior.

    This subagent preserves the full PaperWorkflowRunner capabilities:

    1. paper_answer:
       answer from already indexed local papers.

    2. paper_collect:
       search and download papers, then rebuild the index.

    3. paper_research:
       local-first adaptive workflow:
           local retrieve
             -> evidence sufficiency check
             -> download papers if insufficient
             -> rebuild index
             -> retrieve again
             -> write evidence answer
             -> optionally save report

    In graph multi-agent mode, Planner only needs to route paper-related tasks
    to this subagent. This subagent then decides whether to use local answer,
    collection, or adaptive research.
    """

    name = "paper"
    description = (
        "Answer paper-related questions using local evidence, or run adaptive "
        "paper research that can collect/download/index new papers when needed."
    )

    def __init__(
        self,
        runner: PaperWorkflowRunner,
        max_papers: int = 3,
        min_sources: int = 3,
        force_download: bool = False,
        save_report: bool = True,
    ):
        self.runner = runner
        self.max_papers = max_papers
        self.min_sources = min_sources
        self.force_download = force_download
        self.save_report = save_report

    def run(self, agent_input: SubAgentInput) -> SubAgentOutput:
        blackboard = agent_input.blackboard

        planner_decision = agent_input.metadata.get("planner_decision", {})
        rewritten_request = planner_decision.get("rewritten_request") or ""

        question = self._build_paper_question(
            original_request=blackboard.user_request,
            instruction=agent_input.instruction,
            rewritten_request=rewritten_request,
        )

        search_query = self._build_search_query(
            original_request=blackboard.user_request,
            rewritten_request=rewritten_request,
        )

        mode = self._choose_mode(
            user_request=blackboard.user_request,
            instruction=agent_input.instruction,
            planner_decision=planner_decision,
        )

        self.runner.console.print(f"[cyan]PaperSubAgent mode selected: {mode}[/cyan]")
        self.runner.console.print(
            f"[cyan]PaperSubAgent question preview: {question[:300]}[/cyan]"
        )

        try:
            if mode == "collect":
                self.runner.console.print("[cyan]PaperSubAgent calls paper_collect()[/cyan]")

                state = self.runner.paper_collect(
                    topic=search_query,
                    max_papers=self.max_papers,
                    rebuild_index=True,
                )

            elif mode == "local_answer":
                self.runner.console.print("[cyan]PaperSubAgent calls paper_answer()[/cyan]")

                state = self.runner.paper_answer(
                    question=question,
                    save_report=False,
                )

            else:
                force_download = self._should_force_download(
                    user_request=blackboard.user_request,
                    instruction=agent_input.instruction,
                    planner_decision=planner_decision,
                )

                self.runner.console.print(
                    f"[cyan]PaperSubAgent calls paper_research(force_download={force_download})[/cyan]"
                )

                state = self.runner.paper_research(
                    question=question,
                    search_query=search_query,
                    max_papers=self.max_papers,
                    min_sources=self.min_sources,
                    force_download=force_download,
                    save_report=self.save_report,
                )

            blackboard.merge_agent_state(state)

            answer = state.final_answer or ""

            blackboard.add_note(
                author=self.name,
                content=f"PaperSubAgent completed with mode={mode}.",
                metadata={
                    "mode": mode,
                    "max_papers": self.max_papers,
                    "min_sources": self.min_sources,
                    "force_download": self.force_download,
                    "save_report": self.save_report,
                },
            )

            return SubAgentOutput(
                agent_name=self.name,
                success=True,
                content=answer,
                updates={
                    "paper_mode": mode,
                    "paper_workflow_completed": True,
                    "max_papers": self.max_papers,
                    "min_sources": self.min_sources,
                    "force_download": self.force_download,
                    "save_report": self.save_report,
                },
            )

        except Exception as exc:
            blackboard.add_note(
                author=self.name,
                content=f"PaperSubAgent failed with mode={mode}.",
                metadata={
                    "mode": mode,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )

            return SubAgentOutput(
                agent_name=self.name,
                success=False,
                content="",
                error=f"{type(exc).__name__}: {exc}",
                updates={
                    "paper_mode": mode,
                    "paper_workflow_completed": False,
                },
            )
        
    def _choose_mode(
        self,
        user_request: str,
        instruction: str,
        planner_decision: dict,
    ) -> str:
        """Choose which paper workflow to call."""

        text = "\n".join(
            [
                user_request or "",
                instruction or "",
                str(planner_decision or {}),
            ]
        )

        task_type = str(planner_decision.get("task_type", "")).lower()

        # 当前用户明确要求搜索、找论文、下载、不要本地时，必须进入 adaptive_research。
        if self._force_download_requested(text):
            return "adaptive_research"

        # 只要求下载论文，没有要求解释/总结/回答时，走 collect。
        if self._collect_only_requested(text):
            return "collect"

        # 调研、综述、找论文、相关工作、报告，走 adaptive_research。
        if task_type in {"paper_research", "deep_research", "research_report"}:
            return "adaptive_research"

        if self._research_requested(text):
            return "adaptive_research"

        # 只有明确说“只用本地 / 已有论文 / 不要下载”时，才走 paper_answer。
        if self._strict_local_requested(text):
            return "local_answer"

        # 关键：默认走 paper_research，而不是 paper_answer。
        return "adaptive_research"


    def _should_force_download(
        self,
        user_request: str,
        instruction: str = "",
        planner_decision: dict | None = None,
    ) -> bool:
        if self.force_download:
            return True

        text = "\n".join(
            [
                user_request or "",
                instruction or "",
                str(planner_decision or {}),
            ]
        )

        return self._force_download_requested(text)
    
    @staticmethod
    def _build_paper_question(
        original_request: str,
        instruction: str = "",
        rewritten_request: str = "",
    ) -> str:
        sections: list[str] = []

        if original_request.strip():
            sections.append(
                "Original user request:\n"
                f"{original_request.strip()}"
            )

        if instruction.strip() and instruction.strip() != original_request.strip():
            sections.append(
                "Subagent instruction:\n"
                f"{instruction.strip()}"
            )

        if rewritten_request.strip() and rewritten_request.strip() not in {
            original_request.strip(),
            instruction.strip(),
        }:
            sections.append(
                "Planner rewritten request:\n"
                f"{rewritten_request.strip()}"
            )

        sections.append(
            "Paper workflow instruction:\n"
            "Use the paper workflow to answer the request. Preserve exact paper names, "
            "method names, author names, datasets, and research-topic terms from the "
            "original request. If local indexed evidence is insufficient, the adaptive "
            "paper_research workflow may collect and index new papers before answering."
        )

        return "\n\n".join(sections)

    @staticmethod
    def _build_search_query(
        original_request: str,
        rewritten_request: str = "",
    ) -> str:
        """Build a clean paper search query.

        This query is used only for paper_search / paper_download.
        Do not include workflow instructions or full prompt text here.
        """

        text = rewritten_request.strip() or original_request.strip()

        # Remove common Chinese command words.
        replacements = [
            "搜索一下",
            "搜一下",
            "查一下",
            "查一查",
            "帮我搜索",
            "帮我搜",
            "并告诉我",
            "告诉我",
            "是什么",
            "是啥",
            "请",
            "一下",
        ]

        for item in replacements:
            text = text.replace(item, " ")

        text = " ".join(text.split())

        # Special-case common AI text detection method names.
        # This makes paper search much more stable for short method-name queries.
        if "AdaDetectGPT" in original_request or "AdaDetectGPT" in rewritten_request:
            return "AdaDetectGPT adaptive DetectGPT AI-generated text detection"

        if "DetectGPT" in original_request or "DetectGPT" in rewritten_request:
            return "DetectGPT AI-generated text detection"

        return text

    @staticmethod
    def _strict_local_requested(text: str) -> bool:
        q = text.lower()

        english_keywords = [
            "existing papers",
            "indexed papers",
            "downloaded papers",
            "local papers",
            "local evidence",
            "already indexed",
            "already downloaded",
            "use existing evidence",
            "based on existing papers",
            "based on local papers",
            "do not download",
            "don't download",
            "no download",
        ]

        chinese_keywords = [
            "已有论文",
            "已有文献",
            "本地论文",
            "本地文献",
            "已有证据",
            "本地证据",
            "已经下载",
            "已经索引",
            "基于已有论文",
            "基于已有文献",
            "基于本地论文",
            "基于本地文献",
            "不要下载",
            "不用下载",
            "不要重新下载",
            "不要联网",
            "只用本地",
            "只基于已有",
        ]

        return any(keyword in q for keyword in english_keywords) or any(
            keyword in text for keyword in chinese_keywords
        )


    @staticmethod
    def _collect_only_requested(text: str) -> bool:
        q = text.lower()

        collect_keywords = [
            "collect papers",
            "download papers",
            "download pdf",
            "paper collection",
            "build paper index",
        ]

        chinese_collect_keywords = [
            "收集论文",
            "下载论文",
            "下载几篇",
            "下载pdf",
            "构建论文库",
            "建立论文索引",
            "更新论文索引",
        ]

        answer_keywords = [
            "answer",
            "explain",
            "summarize",
            "summary",
            "review",
            "survey",
            "report",
            "write",
        ]

        chinese_answer_keywords = [
            "回答",
            "解释",
            "总结",
            "综述",
            "报告",
            "分析",
            "写",
            "讲清楚",
            "告诉我",
            "是什么",
            "是啥",
        ]

        wants_collect = any(keyword in q for keyword in collect_keywords) or any(
            keyword in text for keyword in chinese_collect_keywords
        )

        wants_answer = any(keyword in q for keyword in answer_keywords) or any(
            keyword in text for keyword in chinese_answer_keywords
        )

        return wants_collect and not wants_answer


    @staticmethod
    def _research_requested(text: str) -> bool:
        q = text.lower()

        english_keywords = [
            "deep research",
            "paper research",
            "research report",
            "literature review",
            "literature survey",
            "survey",
            "related work",
            "find papers",
            "search papers",
            "collect papers",
            "download papers",
            "academic research",
            "review papers",
        ]

        chinese_keywords = [
            "深度研究",
            "深度调研",
            "调研",
            "研究一下",
            "找论文",
            "搜论文",
            "搜索论文",
            "查论文",
            "去搜索一下论文",
            "搜索一下论文",
            "搜一下论文",
            "收集论文",
            "下载论文",
            "论文调研",
            "文献调研",
            "文献综述",
            "综述",
            "相关工作",
            "课题组汇报",
            "生成报告",
            "写报告",
        ]

        return any(keyword in q for keyword in english_keywords) or any(
            keyword in text for keyword in chinese_keywords
        )


    @staticmethod
    def _force_download_requested(text: str) -> bool:
        q = text.lower()

        english_keywords = [
            "force download",
            "download new papers",
            "search new papers",
            "search papers",
            "find papers",
            "collect papers",
            "search online",
            "web search",
            "online search",
            "look up",
            "look it up",
            "ignore local",
            "do not use local",
            "don't use local",
            "not local",
        ]

        chinese_keywords = [
            # 明确论文搜索
            "强制下载",
            "重新下载",
            "下载新论文",
            "搜索新论文",
            "收集新论文",
            "搜索论文",
            "搜论文",
            "找论文",
            "查论文",
            "去搜索一下论文",
            "搜索一下论文",
            "搜一下论文",
            "找几篇论文",

            # 泛化搜索表达
            "搜索一下",
            "搜一下",
            "查一下",
            "查一查",
            "去搜索一下",
            "去搜一下",
            "帮我搜索",
            "帮我搜",
            "上网搜",
            "网上搜",
            "联网搜",
            "从网上找",
            "网上查",
            "联网查",

            # 排除本地
            "不要本地",
            "不用本地",
            "别用本地",
            "不是本地",
            "不要只用本地",
            "不要在本地",
        ]

        return any(keyword in q for keyword in english_keywords) or any(
            keyword in text for keyword in chinese_keywords
        )
