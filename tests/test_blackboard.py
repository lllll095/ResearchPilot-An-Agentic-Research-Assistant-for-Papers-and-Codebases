import pytest
from research_pilot.multiagent.blackboard import ResearchPilotBlackboard
def test_empty():
    b = ResearchPilotBlackboard(user_request="q")
    assert b.user_request == "q"
def test_note():
    b = ResearchPilotBlackboard(user_request="q")
    b.add_note("planner", "test")
    assert len(b.notes) == 1
def test_code_filter():
    b = ResearchPilotBlackboard(user_request="q")
    b.code_files = ["a.py"]
    b.evidence_sources = ["p.pdf"]
    ctx = b.compact_context(for_subagent="code")
    assert "a.py" in ctx
    assert "p.pdf" not in ctx
def test_paper_filter():
    b = ResearchPilotBlackboard(user_request="q")
    b.code_files = ["a.py"]
    b.evidence_sources = ["p.pdf"]
    ctx = b.compact_context(for_subagent="paper")
    assert "p.pdf" in ctx
    assert "a.py" not in ctx
def test_all():
    b = ResearchPilotBlackboard(user_request="q")
    ctx = b.compact_context()
    assert "q" in ctx
