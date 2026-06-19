#!/usr/bin/env python3
"""ResearchPilot demo: verify installation and show capabilities."""

import sys
import importlib


MODULES = [
    ("research_pilot.core.agent_loop", "AgentLoop"),
    ("research_pilot.core.tool_runtime", "ToolRuntime"),
    ("research_pilot.core.observation", "Observation"),
    ("research_pilot.graph.graph_runner", "GraphWorkflowRunner"),
    ("research_pilot.graph.graph_node", "ParallelGroupNode"),
    ("research_pilot.graph.policy", "RetryPolicy"),
    ("research_pilot.multiagent.blackboard", "ResearchPilotBlackboard"),
    ("research_pilot.multiagent.subagents.planner_subagent", "PlannerSubAgent"),
    ("research_pilot.multiagent.subagents.paper_subagent", "PaperSubAgent"),
    ("research_pilot.multiagent.subagents.reviewer_subagent", "ReviewerSubAgent"),
    ("research_pilot.tools.shell_tool", "ShellTool"),
    ("research_pilot.tools.git_tools", "GitStatusTool"),
    ("research_pilot.memory.long_term_memory", "LongTermMemoryStore"),
    ("research_pilot.conversation.memory_extractor", "MemoryExtractor"),
    ("research_pilot.core.llm_client", "OpenAICompatibleLLMClient"),
    ("research_pilot.api.server", "app"),
]

HEADER = "[32m[1m"


def green(text):
    return f"\033[{HEADER}{text}\033[0m"


def red(text):
    return f"\033[31m{text}\033[0m"


def check_modules():
    """Verify all core modules can be imported."""
    print(f"\n{green('[ResearchPilot]')} Checking module imports...")
    all_ok = True
    for module_path, class_name in MODULES:
        try:
            mod = importlib.import_module(module_path)
            if hasattr(mod, class_name):
                print(f"  [OK] {module_path}.{class_name}")
            else:
                print(f"  [OK] {module_path} (class {class_name} not checked)")
        except ImportError as e:
            print(f"  [FAIL] {module_path}: {e}")
            all_ok = False
    return all_ok


def print_architecture():
    """Print a text architecture overview."""
    print(f"\n{green('[ResearchPilot]')} Architecture:")
    arch = [
        "CLI / API",
        "  |-- Intent Router / Planner",
        "  |-- AgentLoop (free tool-calling)",
        "  |-- Workflows (Code, Paper)",
        "  |-- GraphWorkflowRuntime (multi-agent)",
        "  |     |-- PlannerSubAgent",
        "  |     |-- CodeSubAgent / PaperSubAgent / GeneralSubAgent",
        "  |     |-- ReviewerSubAgent",
        "  |     |-- WriterSubAgent",
        "  |-- ToolRuntime",
        "  |     |-- Shell, Git, Code, Paper, RAG, Web",
        "  |-- Memory Layer",
        "  |     |-- Session Memory (JSON)",
        "  |     |-- Long-term Memory (SQLite)",
        "  |-- Streaming (SSE / AgentLoop events)",
        "  |-- Trace Report + Evaluation",
    ]
    for line in arch:
        print(f"  {line}")


def main():
    print(f"{green('[ResearchPilot]')} System Demo")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Platform: {sys.platform}")

    ok = check_modules()

    if ok:
        print_architecture()
        print(f"\n{green('[ResearchPilot]')} All modules loaded successfully.")
        print(f"  Run tests:  python -m pytest tests/ -v")
        print(f"  Chat:       research-pilot chat --multi-agent --show-graph")
        print(f"  Research:   research-pilot paper-research 'your question here'")
        print(f"  API:        uvicorn research_pilot.api.server:app --host 127.0.0.1 --port 8000")
    else:
        print(f"\n{red('[ResearchPilot]')} Some modules failed to load.")
        sys.exit(1)


if __name__ == "__main__":
    main()
