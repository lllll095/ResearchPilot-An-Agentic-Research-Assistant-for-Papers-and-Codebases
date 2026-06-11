from pathlib import Path

import typer
from rich.console import Console

from research_pilot.agents.mock_agent import MockAgentPolicy
from research_pilot.config import settings
from research_pilot.core.agent_loop import AgentLoop, AgentPolicy
from research_pilot.core.context_manager import ContextManager
from research_pilot.core.hooks import HookManager
from research_pilot.core.permission import PermissionChecker
from research_pilot.core.tool_runtime import ToolRuntime
from research_pilot.core.trace import TraceStore
from research_pilot.tools.file_tools import ListFilesTool, ReadFileTool
from research_pilot.tools.note_tool import SaveNoteTool
from research_pilot.tools.shell_tool import ShellTool
from research_pilot.tools.todo_tool import TodoReadTool, TodoWriteTool
from research_pilot.agents.research_planner_agent import ResearchPlannerAgent
from research_pilot.core.llm_client import OpenAICompatibleLLMClient
from research_pilot.core.state import AgentState
from research_pilot.tools.report_tool import SaveReportTool
from research_pilot.tools.web_search_tool import MockWebSearchTool, TavilyWebSearchTool
from research_pilot.tools.paper_tools import ArxivPaperDownloadTool, ArxivPaperSearchTool
from research_pilot.tools.summarize_tool import SummarizeEvidenceTool
from research_pilot.tools.engineered_rag_tool import (
    EngineeredRAGAnswerTool,
    EngineeredRAGIndexTool,
    EngineeredRAGSearchTool,
)
from research_pilot.tools.evidence_answer_tool import WriteEvidenceAnswerTool
from research_pilot.workflows.paper_workflows import PaperWorkflowRunner
from research_pilot.workflows.intent_router import IntentRouter, IntentType


app = typer.Typer(help="ResearchPilot command line interface.")
console = Console()

def build_paper_workflow_runner() -> PaperWorkflowRunner:
    """Build deterministic paper workflow runner."""

    loop = build_runtime(policy_name="llm")

    return PaperWorkflowRunner(
        tool_runtime=loop.tool_runtime,
        trace_store=loop.trace_store,
        console=console,
    )

def build_policy(policy_name: str) -> AgentPolicy:
    """Build an Agent policy by name."""

    normalized = policy_name.lower().strip()

    if normalized == "mock":
        return MockAgentPolicy()

    if normalized == "llm":
        from research_pilot.agents.llm_agent import LLMAgentPolicy
        from research_pilot.core.llm_client import OpenAICompatibleLLMClient

        llm_client = OpenAICompatibleLLMClient.from_settings()
        return LLMAgentPolicy(llm_client=llm_client)

    raise ValueError(f"Unknown policy: {policy_name}. Use 'mock' or 'llm'.")


def build_runtime(policy_name: str = "mock") -> AgentLoop:
    workspace = Path(settings.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    permission_checker = PermissionChecker(workspace=workspace)
    tool_runtime = ToolRuntime(permission_checker=permission_checker)

    tool_runtime.register(ListFilesTool(permission_checker))
    tool_runtime.register(ReadFileTool(permission_checker))
    tool_runtime.register(SaveNoteTool(workspace / "notes"))
    tool_runtime.register(ShellTool(permission_checker))
    tool_runtime.register(TodoWriteTool())
    tool_runtime.register(TodoReadTool())
    if settings.web_search_backend.lower() == "tavily":
        tool_runtime.register(TavilyWebSearchTool())
    else:
        tool_runtime.register(MockWebSearchTool())
    tool_runtime.register(SaveReportTool(workspace / "reports"))
    tool_llm_client = None
    if policy_name.lower().strip() == "llm":
        tool_llm_client = OpenAICompatibleLLMClient.from_settings()

    tool_runtime.register(SummarizeEvidenceTool(llm_client=tool_llm_client))
    tool_runtime.register(WriteEvidenceAnswerTool(llm_client=tool_llm_client))
    tool_runtime.register(ArxivPaperSearchTool())
    tool_runtime.register(ArxivPaperDownloadTool(workspace / "documents" / "papers"))

    tool_runtime.register(EngineeredRAGIndexTool(workspace=workspace))
    tool_runtime.register(EngineeredRAGSearchTool())
    tool_runtime.register(EngineeredRAGAnswerTool())

    context_manager = ContextManager()
    trace_store = TraceStore(workspace / "traces")
    hook_manager = HookManager()
    policy = build_policy(policy_name)

    return AgentLoop(
        policy=policy,
        tool_runtime=tool_runtime,
        context_manager=context_manager,
        trace_store=trace_store,
        hook_manager=hook_manager,
        max_steps=12,
    )


@app.command()
def run(
    goal: str,
    policy: str = typer.Option(
        "mock",
        "--policy",
        "-p",
        help="Agent policy to use: mock or llm.",
    ),
):
    """Run the Agent Harness."""

    loop = build_runtime(policy_name=policy)
    result = loop.run(goal)

    console.rule("[bold green]Final Answer")
    console.print(result.final_answer)


@app.command()
def tools():
    """List available tools."""

    loop = build_runtime(policy_name="mock")
    specs = loop.tool_runtime.tool_specs()

    console.rule("[bold blue]Available Tools")
    for spec in specs:
        console.print(f"[bold]- {spec.name}[/bold]")
        console.print(f"  {spec.description}")
        console.print(f"  input_schema: {spec.input_schema}")

@app.command()
def research(topic: str):
    """Run a minimal deep research workflow."""

    llm_client = OpenAICompatibleLLMClient.from_settings()
    planner = ResearchPlannerAgent(llm_client=llm_client)

    plan = planner.plan(topic)
    todo_list = planner.to_todo_list(plan)

    console.rule("[bold blue]Research Plan")
    console.print(f"[bold]Topic:[/bold] {plan.topic}")

    for task in plan.tasks:
        console.print(f"- [bold]{task.id}. {task.title}[/bold]")
        console.print(f"  query: {task.query}")

    research_goal = f"""Deep research task:
{topic}

The ResearchPlannerAgent has already decomposed the topic into subtasks and initialized the todo list.

Use web_search to collect evidence for the research subtasks.
Use save_note to save useful intermediate findings.
Use save_report to save the final research report before final_answer.
"""

    state = AgentState(
        user_goal=research_goal,
        todo_list=todo_list,
    )

    loop = build_runtime(policy_name="llm")
    result = loop.run_state(state)

    console.rule("[bold green]Final Answer")
    console.print(result.final_answer)

@app.command("paper-answer")
def paper_answer(
    question: str,
    save_report: bool = typer.Option(
        False,
        "--save-report",
        help="Save the citation-aware answer as a markdown report.",
    ),
    report_title: str | None = typer.Option(
        None,
        "--report-title",
        help="Optional report title.",
    ),
):
    """Answer a question using already indexed papers."""

    runner = build_paper_workflow_runner()
    result = runner.paper_answer(
        question=question,
        save_report=save_report,
        report_title=report_title,
    )

    console.rule("[bold green]Paper Answer")
    console.print(result.final_answer)

@app.command("paper-collect")
def paper_collect(
    topic: str,
    max_papers: int = typer.Option(
        3,
        "--max-papers",
        "-n",
        help="Maximum number of new papers to download.",
    ),
    rebuild_index: bool = typer.Option(
        True,
        "--rebuild-index/--no-rebuild-index",
        help="Whether to rebuild the EngineeredRAG index after downloading.",
    ),
):
    """Search, download, and index papers for a topic."""

    runner = build_paper_workflow_runner()
    result = runner.paper_collect(
        topic=topic,
        max_papers=max_papers,
        rebuild_index=rebuild_index,
    )

    console.rule("[bold green]Paper Collection Result")
    console.print(result.final_answer)

@app.command("paper-research")
def paper_research(
    question: str,
    max_papers: int = typer.Option(
        3,
        "--max-papers",
        "-n",
        help="Maximum number of new papers to download if local evidence is insufficient.",
    ),
    min_sources: int = typer.Option(
        3,
        "--min-sources",
        help="Minimum number of evidence blocks required before skipping download.",
    ),
    force_download: bool = typer.Option(
        False,
        "--force-download",
        help="Always download new papers before answering.",
    ),
    save_report: bool = typer.Option(
        True,
        "--save-report/--no-save-report",
        help="Whether to save the final answer as a report.",
    ),
    report_title: str | None = typer.Option(
        None,
        "--report-title",
        help="Optional report title.",
    ),
):
    """Local-first paper research workflow.

    It first searches indexed papers. If evidence is insufficient, it downloads
    new papers, rebuilds the index, searches again, then writes a citation-aware
    answer and optionally saves a report.
    """

    runner = build_paper_workflow_runner()
    result = runner.paper_research(
        question=question,
        max_papers=max_papers,
        min_sources=min_sources,
        force_download=force_download,
        save_report=save_report,
        report_title=report_title,
    )

    console.rule("[bold green]Paper Research Result")
    console.print(result.final_answer)

@app.command("ask")
def ask(
    user_input: str,
    force_download: bool = typer.Option(
        False,
        "--force-download",
        help="Force downloading new papers before answering.",
    ),
    save_report: bool = typer.Option(
        False,
        "--save-report",
        help="Save the final answer as a report.",
    ),
):
    """Ask ResearchPilot a natural language question.

    This command routes the request to a stable workflow when possible.
    """

    router = IntentRouter()
    routed = router.route(user_input)

    console.print(f"[cyan]Routed intent:[/cyan] {routed.intent_type}")
    console.print(f"[dim]Reason: {routed.reason}[/dim]")

    runner = build_paper_workflow_runner()

    if routed.intent_type == IntentType.PAPER_ANSWER:
        result = runner.paper_answer(
            question=user_input,
            save_report=save_report,
        )

    elif routed.intent_type == IntentType.PAPER_COLLECT:
        result = runner.paper_collect(
            topic=user_input,
            max_papers=routed.max_papers,
            rebuild_index=True,
        )

    elif routed.intent_type == IntentType.PAPER_RESEARCH:
        result = runner.paper_research(
            question=user_input,
            max_papers=routed.max_papers,
            force_download=force_download or routed.force_download,
            save_report=save_report or routed.save_report,
        )

    else:
        console.print(
            "[yellow]Falling back to general Agent run. "
            "For now, use `research-pilot run --policy llm ...` for open-ended tasks.[/yellow]"
        )
        return

    console.rule("[bold green]ResearchPilot Answer")
    console.print(result.final_answer)

if __name__ == "__main__":
    app()