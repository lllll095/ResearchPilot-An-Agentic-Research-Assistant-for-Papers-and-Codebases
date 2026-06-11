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
from research_pilot.tools.web_search_tool import MockWebSearchTool

app = typer.Typer(help="ResearchPilot command line interface.")
console = Console()


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
    tool_runtime.register(MockWebSearchTool())
    tool_runtime.register(SaveReportTool(workspace / "reports"))

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

if __name__ == "__main__":
    app()