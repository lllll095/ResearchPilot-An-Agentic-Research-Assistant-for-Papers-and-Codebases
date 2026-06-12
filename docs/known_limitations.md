# Known Limitations

This document records current limitations of ResearchPilot and possible future improvements.

## 1. Codebase question answering still depends on retrieval quality

The current `code-answer` workflow uses code search results to decide which files should be read before generating the final answer. This works well for localized implementation questions, such as explaining `AgentLoop` or `CodeSearchTool`.

However, for cross-module questions, such as how `ask` routes codebase questions to `code-answer`, the workflow may miss one of the key files if that file is not ranked highly by `code_search`.

Current example:

* Question: `How does the ask command route codebase questions to code-answer?`
* Expected files:

  * `src/research_pilot/workflows/intent_router.py`
  * `src/research_pilot/cli.py`
* Current limitation:

  * The workflow may retrieve the router file but miss the CLI branch.

Future improvement:

* Add targeted multi-search for known routing patterns.
* Add dependency-aware retrieval.
* Add symbol-level search for classes, functions, and CLI commands.

## 2. The LLM may over-infer when evidence is incomplete

The answer writer is instructed to use only provided evidence, but the LLM may still use cautious language such as “likely” when the retrieved code evidence is incomplete.

Future improvement:

* Strengthen the prompt to explicitly reject unsupported inference.
* Add a verification step before final answer generation.
* Add an LLM judge or rule-based checker for unsupported claims.

## 3. Evaluation is useful but not exhaustive

The project currently includes:

* `eval-paper`
* `eval-paper --llm-judge`
* `eval-code`

These checks can catch obvious failures, missing sections, missing citations, missing files, and missing required terms. However, they do not fully prove semantic correctness.

Future improvement:

* Add stronger source-grounding checks.
* Add answer-to-evidence alignment evaluation.
* Add regression tests for critical workflows.

## 4. Some workflows are deterministic by design

ResearchPilot intentionally does not rely entirely on free-form LLM tool use for high-value tasks. Instead, stable tasks are implemented as deterministic workflows.

This improves reliability, but it also means that adding new task types requires explicit workflow design.

Future improvement:

* Add a hybrid planner that can choose among deterministic workflows.
* Add fallback behavior when workflow evidence is insufficient.
* Add richer workflow routing using an LLM classifier.

## 5. External backend integration depends on local environment

The EngineeredRAG backend is integrated through a subprocess worker to avoid Chroma file lock issues on Windows. This design improves robustness, but it still depends on correct local paths, dependencies, and environment variables.

Future improvement:

* Add environment validation commands.
* Add clearer setup diagnostics.
* Add optional Docker support.
