"""Tests for SubAgent pure-logic (no LLM calls)."""

from research_pilot.multiagent.subagents.paper_subagent import PaperSubAgent
from research_pilot.multiagent.subagents.planner_subagent import PlannerSubAgent, PlannerDecision


class TestPaperSubAgentModeSelection:
    """Test PaperSubAgent._choose_mode logic."""

    def _make(self):
        return PaperSubAgent.__new__(PaperSubAgent)

    def test_default_is_adaptive(self):
        mode = self._make()._choose_mode("Tell me about DetectGPT", "", {})
        assert mode == "adaptive_research"

    def test_local_answer(self):
        mode = self._make()._choose_mode("Based on existing papers, what is agentic RAG?", "", {})
        assert mode == "local_answer"

    def test_chinese_local(self):
        mode = self._make()._choose_mode("基于已有论文，agentic RAG的架构是什么？", "", {})
        assert mode == "local_answer"

    def test_force_download(self):
        mode = self._make()._choose_mode("搜索一下并告诉我 AdaDetectGPT 是啥", "", {})
        assert mode == "adaptive_research"

    def test_collect_only(self):
        mode = self._make()._choose_mode("Download papers about agentic RAG", "", {})
        assert mode == "collect"

    def test_planner_research_task_type(self):
        mode = self._make()._choose_mode("What is agentic RAG?", "", {"task_type": "paper_research"})
        assert mode == "adaptive_research"

    def test_chinese_collect_only(self):
        mode = self._make()._choose_mode("下载论文关于Agentic RAG", "", {})
        assert mode == "collect"

    def test_chinese_research(self):
        mode = self._make()._choose_mode("帮我调研一下Agentic RAG的架构", "", {})
        assert mode == "adaptive_research"


class TestPlannerNormalization:
    def test_normalize_valid(self):
        d = PlannerDecision(task_type="code_answer", next_agent="code", reason="x")
        n = PlannerSubAgent._normalize_decision(d)
        assert n.task_type == "code_answer"
        assert n.next_agent == "code"

    def test_invalid_task_type(self):
        d = PlannerDecision(task_type="weird", next_agent="none", reason="x")
        n = PlannerSubAgent._normalize_decision(d)
        assert n.task_type == "general"

    def test_code_implies_task_type(self):
        d = PlannerDecision(task_type="general", next_agent="code", reason="x")
        n = PlannerSubAgent._normalize_decision(d)
        assert n.task_type == "code_answer"
        assert n.next_agent == "code"

    def test_paper_implies_task_type(self):
        d = PlannerDecision(task_type="general", next_agent="paper", reason="x")
        n = PlannerSubAgent._normalize_decision(d)
        assert n.next_agent == "paper"


class TestPlannerFallback:
    def _planner(self):
        p = PlannerSubAgent.__new__(PlannerSubAgent)
        p.name = "planner"
        return p

    def test_fallback_code_en(self):
        d = self._planner()._fallback_decision("How is AgentLoop implemented?", "err")
        assert d.next_agent == "code"

    def test_fallback_code_zh(self):
        d = self._planner()._fallback_decision("AgentLoop是怎么实现的？", "err")
        assert d.next_agent == "code"

    def test_fallback_paper_en(self):
        d = self._planner()._fallback_decision("Find papers about DetectGPT", "err")
        assert d.next_agent == "paper"

    def test_fallback_paper_zh(self):
        d = self._planner()._fallback_decision("找一下关于AdaDetectGPT的论文", "err")
        assert d.next_agent == "paper"

    def test_fallback_general(self):
        d = self._planner()._fallback_decision("What is the weather?", "err")
        assert d.task_type == "general"
        assert d.next_agent == "none"

    def test_fallback_code_over_paper(self):
        d = self._planner()._fallback_decision("How is PaperWorkflowRunner implemented?", "err")
        assert d.next_agent == "code"
