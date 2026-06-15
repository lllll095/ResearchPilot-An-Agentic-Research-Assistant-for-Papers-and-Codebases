# src/research_pilot/evaluation/multiagent_eval.py

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from research_pilot.core.state import AgentState
from research_pilot.workflows.multiagent_workflows import MultiAgentWorkflowRunner


class MultiAgentEvalCase(BaseModel):
    """One multi-agent evaluation case."""

    case_id: str
    question: str
    expected_next_agent: str
    required_terms: list[str] = Field(default_factory=list)
    min_answer_chars: int = 200


class MultiAgentEvalMetrics(BaseModel):
    """Rule-based metrics for one multi-agent case."""

    workflow_success: bool
    answer_long_enough: bool
    has_required_terms: bool

    has_metadata: bool
    has_planner_output: bool
    has_review_output: bool

    planner_selected_expected_agent: bool
    reviewer_ran: bool

    expected_next_agent: str
    actual_next_agent: str | None = None

    review_passed: bool | None = None
    review_confidence: str | None = None

    missing_terms: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(
            [
                self.workflow_success,
                self.answer_long_enough,
                self.has_required_terms,
                self.has_metadata,
                self.has_planner_output,
                self.has_review_output,
                self.planner_selected_expected_agent,
                self.reviewer_ran,
            ]
        )


class MultiAgentEvalResult(BaseModel):
    """Evaluation result for one case."""

    case_id: str
    question: str
    final_answer: str
    metrics: MultiAgentEvalMetrics
    metadata_preview: dict[str, Any] = Field(default_factory=dict)


class MultiAgentEvalSummary(BaseModel):
    """Summary of a multi-agent evaluation run."""

    total: int
    passed: int
    failed: int
    pass_rate: float
    results_path: str
    summary_path: str


class MultiAgentWorkflowEvaluator:
    """Evaluate the multi-agent workflow with rule-based checks."""

    def __init__(
        self,
        runner: MultiAgentWorkflowRunner,
        output_dir: Path,
    ):
        self.runner = runner
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_cases(self, cases_path: Path) -> list[MultiAgentEvalCase]:
        cases: list[MultiAgentEvalCase] = []

        with cases_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line:
                    continue

                cases.append(MultiAgentEvalCase.model_validate_json(line))

        return cases

    def run_cases(
        self,
        cases: list[MultiAgentEvalCase],
        max_cases: int | None = None,
    ) -> MultiAgentEvalSummary:
        if max_cases is not None:
            cases = cases[:max_cases]

        results: list[MultiAgentEvalResult] = []

        for case in cases:
            print(f"[MultiAgentEval] Running case: {case.case_id}")

            result = self._evaluate_case(case)
            results.append(result)

            status = "PASS" if result.metrics.passed else "FAIL"
            print(f"[MultiAgentEval] {case.case_id}: {status}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        results_path = self.output_dir / f"multiagent_eval_results_{timestamp}.json"
        summary_path = self.output_dir / f"multiagent_eval_summary_{timestamp}.md"

        results_path.write_text(
            json.dumps(
                [result.model_dump() for result in results],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        summary_md = self._render_markdown_summary(results)
        summary_path.write_text(summary_md, encoding="utf-8")

        total = len(results)
        passed = sum(1 for result in results if result.metrics.passed)
        failed = total - passed
        pass_rate = passed / total if total else 0.0

        return MultiAgentEvalSummary(
            total=total,
            passed=passed,
            failed=failed,
            pass_rate=pass_rate,
            results_path=str(results_path),
            summary_path=str(summary_path),
        )

    def _evaluate_case(self, case: MultiAgentEvalCase) -> MultiAgentEvalResult:
        state = self.runner.answer(user_request=case.question)

        answer = state.final_answer or ""
        metadata = self._get_metadata(state)

        planner_output = metadata.get("planner_output") or {}
        review_output = metadata.get("review_output") or {}

        actual_next_agent = self._extract_next_agent(planner_output)
        review_result = self._extract_review_result(review_output)

        answer_lower = answer.lower()

        missing_terms = [
            term
            for term in case.required_terms
            if term.lower() not in answer_lower
        ]

        metrics = MultiAgentEvalMetrics(
            workflow_success=bool(answer.strip())
            and "failed" not in answer.lower()
            and "traceback" not in answer.lower(),
            answer_long_enough=len(answer) >= case.min_answer_chars,
            has_required_terms=len(missing_terms) == 0,
            has_metadata=bool(metadata),
            has_planner_output=bool(planner_output),
            has_review_output=bool(review_output),
            planner_selected_expected_agent=actual_next_agent
            == case.expected_next_agent,
            reviewer_ran=bool(review_result),
            expected_next_agent=case.expected_next_agent,
            actual_next_agent=actual_next_agent,
            review_passed=review_result.get("passed")
            if isinstance(review_result, dict)
            else None,
            review_confidence=review_result.get("confidence")
            if isinstance(review_result, dict)
            else None,
            missing_terms=missing_terms,
        )

        return MultiAgentEvalResult(
            case_id=case.case_id,
            question=case.question,
            final_answer=answer,
            metrics=metrics,
            metadata_preview=self._metadata_preview(metadata),
        )

    @staticmethod
    def _get_metadata(state: AgentState) -> dict[str, Any]:
        metadata = getattr(state, "metadata", None)

        if isinstance(metadata, dict):
            return metadata

        return {}

    @staticmethod
    def _extract_next_agent(planner_output: dict[str, Any]) -> str | None:
        updates = planner_output.get("updates") or {}
        decision = updates.get("planner_decision") or {}

        next_agent = decision.get("next_agent")

        if next_agent is None:
            return None

        return str(next_agent)

    @staticmethod
    def _extract_review_result(review_output: dict[str, Any]) -> dict[str, Any]:
        updates = review_output.get("updates") or {}
        review_result = updates.get("review_result") or {}

        if isinstance(review_result, dict):
            return review_result

        return {}

    @staticmethod
    def _metadata_preview(metadata: dict[str, Any]) -> dict[str, Any]:
        preview: dict[str, Any] = {}

        for key in [
            "planner_output",
            "review_output",
            "writer_output",
            "specialist_retry_outputs",
            "specialist_retry_review_outputs",
        ]:
            if key in metadata:
                preview[key] = metadata[key]

        return preview

    def _render_markdown_summary(
        self,
        results: list[MultiAgentEvalResult],
    ) -> str:
        lines = [
            "# Multi-agent Workflow Evaluation Summary",
            "",
            f"Total cases: {len(results)}",
            f"Passed: {sum(1 for result in results if result.metrics.passed)}",
            f"Failed: {sum(1 for result in results if not result.metrics.passed)}",
            "",
            "---",
            "",
        ]

        for result in results:
            status = "PASS" if result.metrics.passed else "FAIL"
            metrics = result.metrics

            lines.extend(
                [
                    f"## {result.case_id}: {status}",
                    "",
                    f"Question: `{result.question}`",
                    "",
                    "### Routing",
                    "",
                    f"- Expected next agent: `{metrics.expected_next_agent}`",
                    f"- Actual next agent: `{metrics.actual_next_agent}`",
                    f"- Planner selected expected agent: {metrics.planner_selected_expected_agent}",
                    "",
                    "### Review",
                    "",
                    f"- Reviewer ran: {metrics.reviewer_ran}",
                    f"- Review passed: {metrics.review_passed}",
                    f"- Review confidence: {metrics.review_confidence}",
                    "",
                    "### Metrics",
                    "",
                    f"- Workflow success: {metrics.workflow_success}",
                    f"- Answer long enough: {metrics.answer_long_enough}",
                    f"- Has required terms: {metrics.has_required_terms}",
                    f"- Has metadata: {metrics.has_metadata}",
                    f"- Has planner output: {metrics.has_planner_output}",
                    f"- Has review output: {metrics.has_review_output}",
                    "",
                ]
            )

            if metrics.missing_terms:
                lines.append(f"Missing terms: {metrics.missing_terms}")
                lines.append("")

            lines.extend(
                [
                    "### Answer Preview",
                    "",
                    "```markdown",
                    result.final_answer[:2000],
                    "```",
                    "",
                    "---",
                    "",
                ]
            )

        return "\n".join(lines)