from pathlib import Path
from io import StringIO

import typer
from rich.console import Console

from research_pilot.agents.llm_agent import LLMAgentPolicy
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
from research_pilot.evaluation.paper_eval import PaperWorkflowEvaluator
from research_pilot.evaluation.llm_judge import PaperAnswerLLMJudge
from research_pilot.tools.codebase_tools import (
    CodeMapTool,
    CodeReadTool,
    CodeSearchTool,
)
from research_pilot.tools.code_answer_tool import WriteCodeAnswerTool
from research_pilot.workflows.code_workflows import CodeWorkflowRunner
from research_pilot.evaluation.code_eval import CodeWorkflowEvaluator
from research_pilot.conversation.conversation_context import ConversationContextBuilder
from research_pilot.conversation.session_store import ConversationSessionStore
from research_pilot.conversation.summarizer import ConversationSummarizer
from research_pilot.core.llm_client import OpenAICompatibleLLMClient
from research_pilot.conversation.turn_memory import TurnMemoryExtractor
from research_pilot.workflows.multiagent_workflows import MultiAgentWorkflowRunner
from research_pilot.evaluation.multiagent_eval import MultiAgentWorkflowEvaluator

app = typer.Typer(help="ResearchPilot command line interface.")
console = Console()

def get_runtime_console(verbose: bool = True) -> Console:
    """Return normal console for verbose mode, otherwise a silent console."""

    if verbose:
        return console

    return Console(
        file=StringIO(),
        force_terminal=False,
        width=120,
    )

def build_paper_workflow_runner(verbose: bool = True) -> PaperWorkflowRunner:
    """Build deterministic paper workflow runner."""

    loop = build_runtime(policy_name="llm")

    return PaperWorkflowRunner(
        tool_runtime=loop.tool_runtime,
        trace_store=loop.trace_store,
        console=get_runtime_console(verbose),
    )

def build_code_workflow_runner(verbose: bool = True) -> CodeWorkflowRunner:
    """Build deterministic code workflow runner."""

    loop = build_runtime(policy_name="llm")

    return CodeWorkflowRunner(
        tool_runtime=loop.tool_runtime,
        trace_store=loop.trace_store,
        console=get_runtime_console(verbose),
    )

def build_multiagent_workflow_runner(
    verbose: bool = True,
) -> MultiAgentWorkflowRunner:
    """Build minimal multi-agent workflow runner."""

    code_runner = build_code_workflow_runner(verbose=verbose)
    paper_runner = build_paper_workflow_runner(verbose=verbose)
    llm_client = OpenAICompatibleLLMClient.from_settings()

    return MultiAgentWorkflowRunner(
        code_workflow_runner=code_runner,
        paper_workflow_runner=paper_runner,
        llm_client=llm_client,
        console=get_runtime_console(verbose),
    )

def build_policy(policy_name: str, tool_runtime=None):
    if policy_name == "mock":
        return MockAgentPolicy()

    if policy_name == "llm":
        from research_pilot.core.llm_client import OpenAICompatibleLLMClient

        llm_client = OpenAICompatibleLLMClient.from_settings()

        tool_specs = []
        if tool_runtime is not None:
            if hasattr(tool_runtime, "list_tool_specs"):
                tool_specs = tool_runtime.list_tool_specs()
            elif hasattr(tool_runtime, "tool_specs"):
                maybe_specs = tool_runtime.tool_specs
                tool_specs = maybe_specs() if callable(maybe_specs) else maybe_specs
            elif hasattr(tool_runtime, "tools"):
                tool_specs = [
                    tool.spec()
                    for tool in tool_runtime.tools.values()
                ]

        return LLMAgentPolicy(
            llm_client=llm_client,
            tool_specs=tool_specs,
        )

    raise ValueError(f"Unknown policy: {policy_name}. Use 'mock' or 'llm'.")


def build_runtime(policy_name: str = "mock", verbose: bool = True) -> AgentLoop:
    workspace = Path(settings.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    permission_checker = PermissionChecker(workspace=workspace)
    tool_runtime = ToolRuntime(permission_checker=permission_checker)

    tool_runtime.register(ListFilesTool(permission_checker))
    tool_runtime.register(ReadFileTool(permission_checker))
    tool_runtime.register(SaveNoteTool(workspace / "notes"))
    tool_runtime.register(ShellTool(permission_checker))
    tool_runtime.register(CodeMapTool())
    tool_runtime.register(CodeSearchTool())
    tool_runtime.register(CodeReadTool())
    
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

    tool_runtime.register(WriteCodeAnswerTool(llm_client=tool_llm_client))

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
    policy = build_policy(policy_name, tool_runtime=tool_runtime)

    return AgentLoop(
        policy=policy,
        tool_runtime=tool_runtime,
        context_manager=context_manager,
        trace_store=trace_store,
        hook_manager=hook_manager,
        max_steps=12,
        console=get_runtime_console(verbose),
    )

def run_ask_request(
    user_input: str,
    max_papers: int = 3,
    min_sources: int = 3,
    force_download: bool = False,
    save_report: bool = False,
    code_path: str = "src/research_pilot",
    verbose: bool = True,
):
    """Run one routed ask request and return the final AgentState."""

    router = IntentRouter()
    routed = router.route(user_input)

    if verbose:
        console.print(f"[cyan]Routed intent:[/cyan] {routed.intent_type}")
        console.print(f"[cyan]Reason:[/cyan] {routed.reason}")

    if routed.intent_type == IntentType.CODE_ANSWER:
        code_runner = build_code_workflow_runner(verbose=verbose)

        return code_runner.code_answer(
            question=user_input,
            path=code_path,
        )

    runner = build_paper_workflow_runner(verbose=verbose)

    if routed.intent_type == IntentType.PAPER_COLLECT:
        return runner.paper_collect(
            topic=user_input,
            max_papers=routed.max_papers or max_papers,
            rebuild_index=True,
        )

    if routed.intent_type == IntentType.PAPER_RESEARCH:
        return runner.paper_research(
            question=user_input,
            max_papers=routed.max_papers or max_papers,
            force_download=force_download or routed.force_download,
            save_report=save_report or routed.save_report,
        )

    if routed.intent_type == IntentType.PAPER_ANSWER:
        return runner.paper_answer(
            question=user_input,
            save_report=save_report or routed.save_report,
        )

    loop = build_runtime(policy_name="llm", verbose=verbose)
    return loop.run(user_input)

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
    max_papers: int = typer.Option(
        3,
        "--max-papers",
        help="Maximum papers to download when needed.",
    ),
    min_sources: int = typer.Option(
        3,
        "--min-sources",
        help="Minimum sources required before skipping download.",
    ),
    force_download: bool = typer.Option(
        False,
        "--force-download",
        help="Force downloading new papers.",
    ),
    save_report: bool = typer.Option(
        False,
        "--save-report",
        help="Save final answer as a report.",
    ),
    code_path: str = typer.Option(
        "src/research_pilot",
        "--code-path",
        help="Code path to inspect when routed to code-answer.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        help="Only print the final answer.",
    ),
):
    """Ask a natural-language question and route it to the right workflow."""

    result = run_ask_request(
        user_input=user_input,
        max_papers=max_papers,
        min_sources=min_sources,
        force_download=force_download,
        save_report=save_report,
        code_path=code_path,
        verbose=not quiet,
    )

    console.rule("[bold green]Answer")
    console.print(result.final_answer)

@app.command("chat")
def chat(
    session_id: str = typer.Option(
        "default",
        "--session",
        "-s",
        help="Conversation session id.",
    ),
    multi_agent: bool = typer.Option(
        False,
        "--multi-agent",
        help="Use the multi-agent planner/subagent workflow.",
    ),
    max_history: int = typer.Option(
        8,
        "--max-history",
        help="Maximum recent messages to inject into the current request.",
    ),
    max_papers: int = typer.Option(
        3,
        "--max-papers",
        help="Maximum papers to download when needed.",
    ),
    force_download: bool = typer.Option(
        False,
        "--force-download",
        help="Force downloading new papers.",
    ),
    save_report: bool = typer.Option(
        False,
        "--save-report",
        help="Save final answer as a report.",
    ),
    code_path: str = typer.Option(
        "src/research_pilot",
        "--code-path",
        help="Code path to inspect when routed to code-answer.",
    ),
    summarize: bool = typer.Option(
        True,
        "--summarize/--no-summarize",
        help="Whether to compress older chat history into a session summary.",
    ),
    summary_keep_recent: int = typer.Option(
        8,
        "--summary-keep-recent",
        help="Number of recent messages to keep outside the compressed summary.",
    ),
    summary_min_new_messages: int = typer.Option(
        4,
        "--summary-min-new-messages",
        help="Minimum new old messages required before updating the summary.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show internal routing and workflow steps.",
    ),
):
    """Start an interactive multi-turn ResearchPilot chat session."""

    store = ConversationSessionStore()
    session = store.load_or_create(session_id)
    context_builder = ConversationContextBuilder(
        max_messages=max_history,
        max_turn_memories=4,
    )
    turn_memory_extractor = TurnMemoryExtractor()
    summarizer = None

    if summarize:
        summarizer = ConversationSummarizer(
            llm_client=OpenAICompatibleLLMClient.from_settings()
        )

    console.print("[bold green]ResearchPilot chat started.[/bold green]")
    console.print(f"[dim]Session: {session.session_id}[/dim]")
    mode_name = "multi-agent" if multi_agent else "single-workflow"
    console.print(f"[dim]Mode: {mode_name}[/dim]")
    console.print("[dim]Type 'exit', 'quit', 'q', or '退出' to stop.[/dim]")

    while True:
        try:
            user_message = console.input("\n[bold cyan]You > [/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Chat stopped.[/yellow]")
            break

        if not user_message:
            continue

        if user_message.lower() in {"exit", "quit", "q", "bye"} or user_message in {
            "退出",
            "结束",
        }:
            console.print("[yellow]Chat stopped.[/yellow]")
            break

        contextual_input = context_builder.build_user_input(
            session=session,
            current_user_input=user_message,
        )

        session.add_message(
            role="user",
            content=user_message,
        )
        store.save(session)

        turn_memory = None

        try:
            if multi_agent:
                runner = build_multiagent_workflow_runner(verbose=verbose)

                result = runner.answer(
                    user_request=contextual_input,
                    session=session,
                )
            else:
                result = run_ask_request(
                    user_input=contextual_input,
                    max_papers=max_papers,
                    force_download=force_download,
                    save_report=save_report,
                    code_path=code_path,
                    verbose=verbose,
                )

            answer = result.final_answer or ""

            turn_memory = turn_memory_extractor.extract(
                user_input=user_message,
                state=result,
            )

        except Exception as exc:
            answer = (
                "The chat turn failed.\n\n"
                f"Error type: {type(exc).__name__}\n"
                f"Error message: {exc}"
            )

        console.print("\n[bold green]Assistant >[/bold green]")
        console.print(answer)

        assistant_metadata = {
            "mode": "chat",
        }

        if turn_memory is not None:
            assistant_metadata["turn_memory"] = turn_memory.model_dump()

        session.add_message(
            role="assistant",
            content=answer,
            metadata=assistant_metadata,
        )

        summary_updated = False

        if summarizer is not None:
            try:
                summary_updated = summarizer.maybe_summarize(
                    session=session,
                    keep_recent=summary_keep_recent,
                    min_new_messages=summary_min_new_messages,
                )
            except Exception as exc:
                console.print(
                    "[yellow]Session summarization failed, but chat history was preserved.[/yellow]"
                )
                console.print(f"[dim]{type(exc).__name__}: {exc}[/dim]")

        path = store.save(session)

        if verbose:
            console.print(f"[dim]Session saved to: {path}[/dim]")

            if summary_updated:
                console.print("[dim]Session summary updated.[/dim]")

@app.command("eval-paper")
def eval_paper(
    cases_path: Path = typer.Option(
        Path("eval/paper_eval_cases.jsonl"),
        "--cases",
        help="Path to JSONL paper evaluation cases.",
    ),
    max_cases: int | None = typer.Option(
        None,
        "--max-cases",
        help="Optional maximum number of cases to run.",
    ),
    use_llm_judge: bool = typer.Option(
        False,
        "--llm-judge",
        help="Use an LLM judge to score groundedness, citation quality, and completeness.",
    ),
):
    """Evaluate paper workflows with rule-based checks and optional LLM judge."""

    runner = build_paper_workflow_runner()

    output_dir = Path(settings.workspace) / "eval_runs"

    judge = None

    if use_llm_judge:
        console.print("[cyan]LLM judge enabled. Creating judge client...[/cyan]")
        judge = PaperAnswerLLMJudge(
            llm_client=OpenAICompatibleLLMClient.from_settings()
        )
    else:
        console.print("[dim]LLM judge disabled. Running rule-based evaluation only.[/dim]")

    evaluator = PaperWorkflowEvaluator(
        runner=runner,
        output_dir=output_dir,
        llm_judge=judge,
    )

    cases = evaluator.load_cases(cases_path)
    summary = evaluator.run_cases(
        cases=cases,
        max_cases=max_cases,
    )

    console.rule("[bold green]Paper Evaluation Summary")
    console.print(f"Total: {summary.total}")
    console.print(f"Passed: {summary.passed}")
    console.print(f"Failed: {summary.failed}")
    console.print(f"Pass rate: {summary.pass_rate:.1%}")
    console.print(f"Results: {summary.results_path}")
    console.print(f"Summary: {summary.summary_path}")

@app.command("code-answer")
def code_answer(
    question: str,
    path: str = typer.Option(
        "src/research_pilot",
        "--path",
        help="Project path to inspect.",
    ),
    max_results: int = typer.Option(
        20,
        "--max-results",
        help="Maximum code search matches.",
    ),
    max_files: int = typer.Option(
        3,
        "--max-files",
        help="Maximum matched files to read.",
    ),
):
    """Answer a question about the codebase using deterministic code workflow."""

    runner = build_code_workflow_runner()

    result = runner.code_answer(
        question=question,
        path=path,
        max_results=max_results,
        max_files_to_read=max_files,
    )

    console.rule("[bold green]Code Answer")
    console.print(result.final_answer)

@app.command("eval-code")
def eval_code(
    cases_path: Path = typer.Option(
        Path("eval/code_eval_cases.jsonl"),
        "--cases",
        help="Path to JSONL code evaluation cases.",
    ),
    max_cases: int | None = typer.Option(
        None,
        "--max-cases",
        help="Optional maximum number of cases to run.",
    ),
):
    """Evaluate code-answer workflow with rule-based checks."""

    runner = build_code_workflow_runner()

    output_dir = Path(settings.workspace) / "eval_runs"

    evaluator = CodeWorkflowEvaluator(
        runner=runner,
        output_dir=output_dir,
    )

    cases = evaluator.load_cases(cases_path)
    summary = evaluator.run_cases(
        cases=cases,
        max_cases=max_cases,
    )

    console.rule("[bold green]Code Evaluation Summary")
    console.print(f"Total: {summary.total}")
    console.print(f"Passed: {summary.passed}")
    console.print(f"Failed: {summary.failed}")
    console.print(f"Pass rate: {summary.pass_rate:.1%}")
    console.print(f"Results: {summary.results_path}")
    console.print(f"Summary: {summary.summary_path}")


@app.command("session-show")
def session_show(
    session_id: str = typer.Option(
        "default",
        "--session",
        "-s",
        help="Conversation session id.",
    ),
    max_messages: int = typer.Option(
        10,
        "--max-messages",
        help="Maximum recent raw messages to show.",
    ),
    show_memory: bool = typer.Option(
        True,
        "--show-memory/--no-show-memory",
        help="Show compact structured turn memory.",
    ),
):
    """Show a saved conversation session."""

    store = ConversationSessionStore()
    session = store.load_or_create(session_id)

    console.rule(f"[bold green]Session: {session.session_id}")

    console.print(f"[cyan]Created:[/cyan] {session.created_at}")
    console.print(f"[cyan]Updated:[/cyan] {session.updated_at}")
    console.print(f"[cyan]Messages:[/cyan] {len(session.messages)}")
    console.print(
        f"[cyan]Summarized message count:[/cyan] "
        f"{session.metadata.get('summarized_message_count', 0)}"
    )

    console.rule("[bold blue]Summary")
    console.print(session.summary or "[dim](empty)[/dim]")

    console.rule("[bold blue]Recent Messages")

    for message in session.recent_messages(max_messages):
        console.print(f"[bold]{message.role}[/bold] [{message.created_at}]")
        console.print(message.content[:1500])
        if len(message.content) > 1500:
            console.print("[dim]... truncated ...[/dim]")
        console.print()

    # 这一段放在 Recent Messages 的 for 循环之后。
    # 注意：if show_memory 要和上面的 for message 对齐，不要缩进到 for 里面。
    if show_memory:
        console.rule("[bold blue]Recent Turn Memory")

        count = 0

        for message in reversed(session.messages):
            if message.role != "assistant":
                continue

            memory = message.metadata.get("turn_memory")
            if not isinstance(memory, dict):
                continue

            count += 1
            console.print(f"[bold]Turn memory {count}[/bold]")

            user_input = memory.get("user_input")
            if user_input:
                console.print(f"[cyan]User input:[/cyan] {user_input}")

            code_files = memory.get("code_files") or []
            if code_files:
                console.print("[cyan]Code files:[/cyan]")
                for file in code_files[:10]:
                    console.print(f"- {file}")

            code_search_queries = memory.get("code_search_queries") or []
            if code_search_queries:
                console.print("[cyan]Code search queries:[/cyan]")
                for query in code_search_queries[:10]:
                    console.print(f"- {query}")

            evidence_sources = memory.get("evidence_sources") or []
            if evidence_sources:
                console.print("[cyan]Evidence sources:[/cyan]")
                for source in evidence_sources[:10]:
                    console.print(f"- {source}")

            report_paths = memory.get("report_paths") or []
            if report_paths:
                console.print("[cyan]Report paths:[/cyan]")
                for path in report_paths[:10]:
                    console.print(f"- {path}")

            console.print()

            if count >= 5:
                break

        if count == 0:
            console.print("[dim](no structured turn memory found)[/dim]")

@app.command("multi-agent")
def multi_agent(
    user_input: str,
    session_id: str | None = typer.Option(
        None,
        "--session",
        "-s",
        help="Optional conversation session id.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show internal workflow logs.",
    ),
):
    """Run the minimal multi-agent workflow."""

    session = None

    if session_id:
        store = ConversationSessionStore()
        session = store.load_or_create(session_id)

    runner = build_multiagent_workflow_runner(verbose=verbose)

    result = runner.answer(
        user_request=user_input,
        session=session,
    )

    console.print("\n[bold green]Assistant >[/bold green]")
    console.print(result.final_answer)

@app.command("eval-multi-agent")
def eval_multi_agent(
    cases_path: Path = typer.Option(
        Path("eval/multiagent_eval_cases.jsonl"),
        "--cases",
        help="Path to JSONL multi-agent evaluation cases.",
    ),
    max_cases: int | None = typer.Option(
        None,
        "--max-cases",
        help="Optional maximum number of cases to run.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show internal workflow logs.",
    ),
):
    """Evaluate multi-agent workflow with rule-based checks."""

    runner = build_multiagent_workflow_runner(verbose=verbose)

    output_dir = Path(settings.workspace) / "eval_runs"

    evaluator = MultiAgentWorkflowEvaluator(
        runner=runner,
        output_dir=output_dir,
    )

    cases = evaluator.load_cases(cases_path)
    summary = evaluator.run_cases(
        cases=cases,
        max_cases=max_cases,
    )

    console.rule("[bold green]Multi-agent Evaluation Summary")
    console.print(f"Total: {summary.total}")
    console.print(f"Passed: {summary.passed}")
    console.print(f"Failed: {summary.failed}")
    console.print(f"Pass rate: {summary.pass_rate:.1%}")
    console.print(f"Results: {summary.results_path}")
    console.print(f"Summary: {summary.summary_path}")

if __name__ == "__main__":
    app()