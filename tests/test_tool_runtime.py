"""Tests for ToolRuntime."""

import pytest

from pathlib import Path

from research_pilot.core.tool_runtime import ToolRuntime
from research_pilot.core.permission import PermissionChecker
from research_pilot.core.tool import BaseTool, ToolSpec
from research_pilot.core.action import AgentAction, ActionType
from research_pilot.core.observation import Observation


class DummyTool(BaseTool):
    """A tool that returns a fixed response."""

    def __init__(self, name: str = "dummy"):
        self.name = name

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description="Dummy tool for testing.")

    def run(self, tool_input: dict, state=None) -> Observation:
        return Observation(
            success=True,
            content="dummy result",
            metadata={"tool": self.name},
        )


class FailingTool(BaseTool):
    """A tool that always fails."""

    def __init__(self, name: str = "failing"):
        self.name = name

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description="A tool that always fails.")

    def run(self, tool_input: dict, state=None) -> Observation:
        return Observation(
            success=False,
            content="",
            error="Intentional failure",
        )


@pytest.fixture
def tool_runtime():
    permission_checker = PermissionChecker(workspace=Path("/tmp/test"))
    return ToolRuntime(permission_checker=permission_checker)


class TestToolRuntime:
    """Tests for tool registration and execution."""

    def test_register_and_list(self, tool_runtime):
        tool_runtime.register(DummyTool("test_tool"))
        tools = tool_runtime.list_tools()
        assert "test_tool" in tools

    def test_duplicate_registration_raises(self, tool_runtime):
        tool_runtime.register(DummyTool("dup"))
        with pytest.raises(ValueError, match="already registered"):
            tool_runtime.register(DummyTool("dup"))

    def test_execute_registered_tool(self, tool_runtime):
        tool_runtime.register(DummyTool("greet"))

        action = AgentAction(
            action_type=ActionType.TOOL_CALL,
            tool_name="greet",
            tool_input={"name": "world"},
        )

        observation = tool_runtime.execute(action)

        assert observation.success is True
        assert "dummy result" in observation.content

    def test_execute_unregistered_tool(self, tool_runtime):
        action = AgentAction(
            action_type=ActionType.TOOL_CALL,
            tool_name="nonexistent",
        )

        observation = tool_runtime.execute(action)

        assert observation.success is False
        assert "ToolNotFound" == observation.error

    def test_execute_without_tool_name(self, tool_runtime):
        action = AgentAction(
            action_type=ActionType.TOOL_CALL,
            tool_name=None,
        )

        observation = tool_runtime.execute(action)

        assert observation.success is False
        assert "No tool name" in observation.content

    def test_failing_tool(self, tool_runtime):
        tool_runtime.register(FailingTool("will_fail"))

        action = AgentAction(
            action_type=ActionType.TOOL_CALL,
            tool_name="will_fail",
        )

        observation = tool_runtime.execute(action)

        assert observation.success is False
        assert "Intentional failure" in observation.error

    def test_tool_specs(self, tool_runtime):
        tool_runtime.register(DummyTool("alpha"))
        tool_runtime.register(DummyTool("beta"))

        specs = tool_runtime.tool_specs()
        names = [s.name for s in specs]

        assert "alpha" in names
        assert "beta" in names
        assert len(specs) == 2

class TestToolValidation:
    def test_valid_input_passes(self, tool_runtime):
        from research_pilot.core.tool import BaseTool, ToolSpec
        from research_pilot.core.action import AgentAction, ActionType
        class VT(BaseTool):
            name = "vt"
            def spec(self):
                return ToolSpec(name="vt", description="T", input_schema={"n": "name"})
            def run(self, ti, state=None):
                return Observation(success=True, content="ok", data={"n": ti["n"]})
        tool_runtime.register(VT())
        obs = tool_runtime.execute(AgentAction(action_type=ActionType.TOOL_CALL, tool_name="vt", tool_input={"n": "A"}))
        assert obs.success is True
    def test_missing_input_fails(self, tool_runtime):
        from research_pilot.core.tool import BaseTool, ToolSpec
        from research_pilot.core.action import AgentAction, ActionType
        class ST(BaseTool):
            name = "st"
            def spec(self):
                return ToolSpec(name="st", description="T", input_schema={"req": "required"})
            def run(self, ti, state=None):
                return Observation(success=True, content="ok")
        tool_runtime.register(ST())
        obs = tool_runtime.execute(AgentAction(action_type=ActionType.TOOL_CALL, tool_name="st", tool_input={}))
        assert obs.success is False
        assert obs.error == "InputValidationError"
    def test_output_schema_valid(self, tool_runtime):
        from research_pilot.core.tool import BaseTool, ToolSpec
        from research_pilot.core.action import AgentAction, ActionType
        class OT(BaseTool):
            name = "ot"
            def spec(self):
                return ToolSpec(name="ot", description="T", input_schema={}, output_schema={"r": "result"})
            def run(self, ti, state=None):
                return Observation(success=True, content="d", data={"r": 42})
        tool_runtime.register(OT())
        obs = tool_runtime.execute(AgentAction(action_type=ActionType.TOOL_CALL, tool_name="ot", tool_input={}))
        assert obs.success is True
    def test_output_schema_missing_fails(self, tool_runtime):
        from research_pilot.core.tool import BaseTool, ToolSpec
        from research_pilot.core.action import AgentAction, ActionType
        class BT(BaseTool):
            name = "bt"
            def spec(self):
                return ToolSpec(name="bt", description="T", input_schema={}, output_schema={"rk": "must"})
            def run(self, ti, state=None):
                return Observation(success=True, content="d", data={"wk": "v"})
        tool_runtime.register(BT())
        obs = tool_runtime.execute(AgentAction(action_type=ActionType.TOOL_CALL, tool_name="bt", tool_input={}))
        assert obs.success is False
        assert "rk" in obs.content


class TestShellTool:
    def test_shell_basic(self, tmp_path):
        from research_pilot.tools.shell_tool import ShellTool
        from research_pilot.core.permission import PermissionChecker
        tool = ShellTool(PermissionChecker(workspace=tmp_path), timeout=10)
        obs = tool.run({"command": "echo hello"})
        assert obs.success is True
        assert "hello" in obs.content

    def test_shell_missing_command(self, tmp_path):
        from research_pilot.tools.shell_tool import ShellTool
        from research_pilot.core.permission import PermissionChecker
        tool = ShellTool(PermissionChecker(workspace=tmp_path), timeout=10)
        obs = tool.run({})
        assert obs.success is False
        assert "MissingCommand" in obs.error

    def test_shell_with_cwd(self, tmp_path):
        from research_pilot.tools.shell_tool import ShellTool
        from research_pilot.core.permission import PermissionChecker
        (tmp_path / "test.txt").write_text("content", encoding="utf-8")
        tool = ShellTool(PermissionChecker(workspace=tmp_path), timeout=10)
        obs = tool.run({"command": "type test.txt", "cwd": str(tmp_path)})
        assert obs.success is True

    def test_shell_bg_and_list(self, tmp_path):
        from research_pilot.tools.shell_tool import ShellTool, ShellBgTool
        from research_pilot.core.permission import PermissionChecker
        tool = ShellTool(PermissionChecker(workspace=tmp_path), timeout=10)
        bg_obs = tool.run({"command": "python --version", "background": "true"})
        assert bg_obs.success is True
        assert "bg_" in bg_obs.content
        bg_id = bg_obs.data.get("bg_id")

        bg_tool = ShellBgTool()
        list_obs = bg_tool.run({"action": "list"})
        assert list_obs.success is True
        assert bg_id in list_obs.content

        # Clean up
        bg_tool.run({"action": "kill", "bg_id": bg_id})
