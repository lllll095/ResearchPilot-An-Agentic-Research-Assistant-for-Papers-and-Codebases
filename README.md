# ResearchPilot：图工作流驱动的多智能体研究助手

ResearchPilot 是一个面向代码理解、论文研究、证据生成和多轮对话的 Agent Engineering 项目。

它不是一个简单的 RAG demo，而是从底层 AgentLoop、ToolRuntime、Workflow、GraphWorkflowRuntime 到 Multi-agent Blackboard、Conversation Memory、Evaluation 和 Trace Report 的完整工程实践。

项目核心目标是构建一个可运行、可调试、可评估、可扩展的研究型 Agent 系统。

---

## 1. 项目亮点

ResearchPilot 当前实现了：

* 自定义 AgentLoop：支持 LLM policy、tool calling、AgentState、Observation、TraceStore
* ToolRuntime：统一管理和执行工具
* Deterministic Workflow：稳定的代码问答和论文研究流程
* GraphWorkflowRuntime：轻量级图工作流运行时，支持条件分支、循环、retry
* Multi-agent Blackboard：基于共享黑板的多智能体协作机制
* SubAgent 系统：Planner、Code、Paper、General、Reviewer、Writer
* Adaptive Paper Research：本地检索不足时自动搜索、下载、索引论文并重新生成答案
* Codebase QA：支持代码搜索、文件阅读和基于代码证据的回答
* Conversation Memory：支持持久化 session、summary、turn memory 和证据继承
* Trace Report：保存 multi-agent 执行路径、planner 决策、reviewer 结果和 blackboard 状态
* Evaluation：支持 code、paper、multi-agent workflow 的回归测试

---

## 2. 核心架构

ResearchPilot 当前包含三层执行架构：

```text
第一层：AgentLoop
  通用自由工具调用循环，适合开放式任务。

第二层：Deterministic Workflow
  稳定任务流，适合代码问答、论文问答、论文研究。

第三层：Graph Workflow
  图结构多智能体编排，支持分支、循环、review、retry 和 writer fallback。
```

整体流程可以理解为：

```text
CLI / Chat
  ↓
Intent Router 或 PlannerSubAgent
  ↓
AgentLoop / CodeWorkflow / PaperWorkflow / GraphWorkflow
  ↓
ToolRuntime
  ↓
Tools
  ↓
Observation / EvidenceStore / TraceStore
  ↓
Final Answer / Report / Session Memory
```

---

## 3. 多智能体图工作流

当前主线入口默认使用 Graph-based Multi-agent Workflow。

典型执行路径：

```text
prepare
  ↓
planner
  ↓
code / paper / general
  ↓
reviewer
  ↓
final / retry / writer
```

其中：

```text
PlannerSubAgent
  判断用户问题应该交给哪个 specialist。

CodeSubAgent
  调用 CodeWorkflowRunner 完成代码库问答。

PaperSubAgent
  调用 PaperWorkflowRunner 完成论文检索、下载、索引和证据生成。

GeneralSubAgent
  处理普通问题兜底。

ReviewerSubAgent
  检查答案是否相关、充分、被证据支持。

WriterSubAgent
  在 reviewer 认为答案不足时进行最终改写。
```

---

## 4. Adaptive Paper Research

论文研究是项目中的重点能力。

PaperWorkflowRunner 支持三种模式：

```text
paper_answer:
  只基于已有本地论文索引回答。

paper_collect:
  搜索并下载论文，更新论文库。

paper_research:
  local-first adaptive research workflow。
```

`paper_research` 的流程是：

```text
local engineered_rag_search
  ↓
evidence sufficiency check
  ↓
如果证据不足或用户明确要求搜索：
      paper_download
      engineered_rag_index
      engineered_rag_search
  ↓
write_evidence_answer
  ↓
如果 writer 判断证据仍不足：
      fallback 到 download / index / search / answer
  ↓
save_report
```

这个设计解决了普通 RAG 中常见的问题：

```text
top-k retrieval 不等于证据充分；
本地检索返回多个 chunk 不代表真的回答了问题；
生成器发现证据不足后，需要反馈给 workflow 继续检索。
```

---

## 5. Codebase QA

代码问答流程由 CodeWorkflowRunner 管理。

典型流程：

```text
code_map
  ↓
code_search
  ↓
code_read
  ↓
write_code_answer
```

可以回答：

```text
AgentLoop 是怎么实现的？
ToolRuntime 是怎么执行工具的？
某个 workflow 的调用链是什么？
某个类或函数在哪里？
为什么某个报错会出现？
```

---

## 6. Conversation Memory

ResearchPilot 支持持久化多轮对话。

相关能力包括：

```text
session 持久化
recent messages
session summary
turn memory
code files carryover
evidence sources carryover
report paths carryover
```

在 graph multi-agent chat 中，当前用户消息作为 `user_request` 传入 graph runner，历史上下文通过 session 进入 blackboard，避免把完整历史拼进当前问题导致路由污染。

---

## 7. Trace Report

ResearchPilot 可以保存 multi-agent trace report。

Trace report 中包含：

```text
用户请求
最终答案
graph visited path
planner decision
specialist output
reviewer result
retry path
writer output
blackboard summary
metadata preview
```

这让复杂 agent workflow 具备较强的可解释性和可调试性。

---

## 8. Evaluation

项目包含多类回归测试：

```text
eval-code
eval-paper
eval-multi-agent
```

Evaluation 可以检查：

```text
workflow 是否成功
planner 是否路由正确
answer 是否包含关键术语
metadata 是否保留
reviewer 是否运行
graph visited nodes 是否存在
```

这使项目从“能跑的 demo”变成“可测试的 agent system”。

---

## 9. 常用命令

### 9.1 多智能体对话

```powershell
research-pilot chat --multi-agent
```

显示 graph 路径和 planner 决策：

```powershell
research-pilot chat --multi-agent --show-graph --show-plan
```

显示更多调试信息：

```powershell
research-pilot chat --multi-agent --show-graph --show-plan --show-review --verbose
```

保存 trace report：

```powershell
research-pilot chat --multi-agent --save-trace-report
```

---

### 9.2 单次多智能体运行

```powershell
research-pilot multi-agent "AgentLoop 是怎么实现的？"
```

```powershell
research-pilot multi-agent "搜索一下并告诉我 AdaDetectGPT 是啥" --show-graph --show-plan --verbose
```

---

### 9.3 代码问答

```powershell
research-pilot code-answer "AgentLoop 是怎么实现的？"
```

```powershell
research-pilot code-answer "ToolRuntime 是怎么执行工具的？"
```

---

### 9.4 论文问答与研究

基于已有论文证据回答：

```powershell
research-pilot paper-answer "基于已有论文证据，agentic RAG 的架构是什么？"
```

完整论文研究流程：

```powershell
research-pilot paper-research "搜索一下并告诉我 AdaDetectGPT 是啥"
```

收集论文：

```powershell
research-pilot paper-collect "DetectGPT AI-generated text detection"
```

---

### 9.5 Evaluation

```powershell
research-pilot eval-code
```

```powershell
research-pilot eval-paper
```

```powershell
research-pilot eval-multi-agent
```

---

## 10. 推荐 Demo

### Demo 1：代码理解

```powershell
research-pilot chat --multi-agent --show-graph --show-plan
```

输入：

```text
AgentLoop 是怎么实现的？
```

预期路径：

```text
prepare → planner → code → reviewer → final
```

---

### Demo 2：论文研究

```powershell
research-pilot chat --multi-agent --show-graph --show-plan --verbose
```

输入：

```text
搜索一下并告诉我 AdaDetectGPT 是啥
```

预期路径：

```text
prepare → planner → paper → reviewer → final
```

PaperSubAgent 内部会调用：

```text
paper_research
  → paper_download
  → engineered_rag_index
  → engineered_rag_search
  → write_evidence_answer
```

---

### Demo 3：普通问题兜底

```powershell
research-pilot chat --multi-agent --show-graph --show-plan
```

输入：

```text
RAG 和 Agent 的区别是什么？
```

预期路径：

```text
prepare → planner → general → final
```

---

## 11. 项目目录结构

```text
src/research_pilot/
  agents/                 # LLM policy、writer、summarizer 等组件
  core/                   # AgentLoop、State、Action、ToolRuntime、Trace
  tools/                  # code、paper、RAG、save 等工具
  workflows/              # code workflow、paper workflow、multi-agent workflow
  graph/                  # GraphWorkflowRuntime
  multiagent/             # Blackboard、SubAgent、Trace Report
  conversation/           # session、summary、turn memory
  evaluation/             # eval-code、eval-paper、eval-multi-agent
docs/
  project_architecture.md # 项目架构说明
eval/
  *_eval_cases.jsonl      # evaluation cases
```

---

## 12. 和普通 RAG demo 的区别

普通 RAG demo 通常是：

```text
load documents
  ↓
retrieve top-k chunks
  ↓
LLM answer
```

ResearchPilot 更接近完整 agent system：

```text
Planner 路由
  ↓
PaperSubAgent / CodeSubAgent
  ↓
Adaptive Workflow
  ↓
ToolRuntime
  ↓
Evidence Store
  ↓
Reviewer
  ↓
Retry / Writer
  ↓
Trace Report
  ↓
Evaluation
```

核心区别是：

```text
ResearchPilot 不只关注“回答”，还关注：
  如何规划
  如何检索
  如何判断证据是否充分
  如何失败回退
  如何追踪过程
  如何评估结果
```

---

## 13. 当前限制

当前项目仍有一些可以继续优化的地方：

```text
1. subagent 还没有完整 message isolation。
2. paper search 主要依赖 arXiv API，候选排序仍可增强。
3. indexing 目前是同步执行。
4. incremental-only indexing 可以进一步优化。
5. fast search answer 和 full RAG answer 还没有完全拆开。
6. reviewer 只是启发式审查，不是形式化正确性保证。
```

---

## 14. 后续扩展方向

后续可以继续做：

```text
SubAgent Context Isolation
Fast Paper Search Answer
Background Paper Indexing
Incremental-only RAG Index
Paper Candidate Reranking
LLM Evidence Grader
Graph Visualization
Evaluation Dashboard
Parallel SubAgent Execution
```

---

## 15. 项目总结

ResearchPilot 是一个自定义 Agent Engineering 项目，包含：

```text
AgentLoop
ToolRuntime
Deterministic Workflow
GraphWorkflowRuntime
Blackboard Multi-agent
Conversation Memory
Adaptive Paper Research
Codebase QA
Evidence-aware Answer Generation
Trace Report
Evaluation
```

它的核心价值不是某一个 prompt 或某一个 RAG pipeline，而是完整展示了一个复杂 agent 系统从底层运行时到上层多智能体编排的工程实现过程。
