# src/research_pilot/prompts/agent_prompt.py

from typing import Any

from research_pilot.prompts.prompt_sections import (
    ACTION_SCHEMA_GUARD_RULES,
    ACTION_SCHEMA_PROMPT,
    BASE_POLICY_IDENTITY,
    CODE_ANSWER_RULES,
    CODEBASE_RULES,
    ENGINEERED_RAG_RULES,
    EVIDENCE_ANSWER_RULES,
    GENERAL_TOOL_RULES,
    PAPER_RULES,
    RESEARCH_RULES,
    TODO_RULES,
)
from research_pilot.prompts.tool_prompt import render_tool_specs


class AgentSystemPromptBuilder:
    """Build the system prompt for the general LLM agent policy.

    This builder keeps the original behavior of the monolithic prompt,
    but splits prompt sections into reusable modules.
    """

    def __init__(
        self,
        tool_specs: Any,
        include_todo_rules: bool = True,
        include_research_rules: bool = True,
        include_paper_rules: bool = True,
        include_engineered_rag_rules: bool = True,
        include_evidence_answer_rules: bool = True,
        include_codebase_rules: bool = True,
        include_code_answer_rules: bool = True,
    ):
        self.tool_specs = tool_specs
        self.include_todo_rules = include_todo_rules
        self.include_research_rules = include_research_rules
        self.include_paper_rules = include_paper_rules
        self.include_engineered_rag_rules = include_engineered_rag_rules
        self.include_evidence_answer_rules = include_evidence_answer_rules
        self.include_codebase_rules = include_codebase_rules
        self.include_code_answer_rules = include_code_answer_rules

    def build(self) -> str:
        sections = [
            BASE_POLICY_IDENTITY,
            ACTION_SCHEMA_PROMPT,
        ]

        if self.include_todo_rules:
            sections.append(TODO_RULES)

        if self.include_research_rules:
            sections.append(RESEARCH_RULES)

        if self.include_paper_rules:
            sections.append(PAPER_RULES)

        if self.include_engineered_rag_rules:
            sections.append(ENGINEERED_RAG_RULES)

        if self.include_evidence_answer_rules:
            sections.append(EVIDENCE_ANSWER_RULES)

        if self.include_codebase_rules:
            sections.append(CODEBASE_RULES)

        if self.include_code_answer_rules:
            sections.append(CODE_ANSWER_RULES)

        sections.extend(
            [
                ACTION_SCHEMA_GUARD_RULES,
                render_tool_specs(self.tool_specs),
                GENERAL_TOOL_RULES,
            ]
        )

        return "\n\n".join(
            section.strip()
            for section in sections
            if section and section.strip()
        )