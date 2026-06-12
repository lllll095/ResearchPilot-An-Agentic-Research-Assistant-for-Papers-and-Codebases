# src/research_pilot/prompts/tool_prompt.py

from typing import Any


def render_tool_specs(tool_specs: Any) -> str:
    """Render available tool specs into a compact prompt section."""

    specs = _normalize_tool_specs(tool_specs)

    if not specs:
        return "Available tools:\n- No tools were provided."

    lines = ["Available tools:"]

    for spec in specs:
        name = spec.get("name", "")
        description = spec.get("description", "")
        input_schema = spec.get("input_schema") or spec.get("parameters") or {}

        lines.append("")
        lines.append(f"- Tool name: {name}")
        lines.append(f"  Description: {description}")

        if input_schema:
            lines.append(f"  Input schema: {input_schema}")

    return "\n".join(lines)


def _normalize_tool_specs(tool_specs: Any) -> list[dict[str, Any]]:
    """Convert tool specs from dict/list/object forms into dictionaries."""

    if tool_specs is None:
        return []

    normalized: list[dict[str, Any]] = []

    if isinstance(tool_specs, dict):
        iterable = tool_specs.values()
    else:
        iterable = tool_specs

    for spec in iterable:
        if isinstance(spec, dict):
            normalized.append(spec)
            continue

        item = {
            "name": getattr(spec, "name", ""),
            "description": getattr(spec, "description", ""),
        }

        input_schema = getattr(spec, "input_schema", None)
        if input_schema is not None:
            item["input_schema"] = input_schema

        parameters = getattr(spec, "parameters", None)
        if parameters is not None:
            item["parameters"] = parameters

        normalized.append(item)

    return normalized