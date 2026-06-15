# ResearchPilot 项目架构说明

## 1. 项目概述

ResearchPilot 是一个面向代码理解、论文研究、证据生成和多轮对话的图工作流多智能体研究助手。

它不是一个简单的 RAG demo，而是一个完整的 Agent Engineering 项目。项目从最早的通用 AgentLoop 出发，逐步扩展出工具执行层、确定性 workflow、多智能体 graph runtime、黑板共享状态、对话记忆、证据管理、trace report 和 evaluation。

当前系统的核心思想是：

```text
用 AgentLoop 保留开放式工具调用能力；
用 deterministic workflow 提高稳定性和降低 token 消耗；
用 graph workflow 管理多智能体分支、循环、审查和重试；
用 blackboard 和 trace report 让整个过程可观察、可调试、可复盘。
```

---

## 2. 总体架构

ResearchPilot 当前可以分成三层执行架构：

```text
第一层：AgentLoop
  通用自由工具调用循环，适合开放式任务。

第二层：Deterministic Workflow
  稳定任务流，适合代码问答、论文问答、论文研究。

第三层：Graph Workflow
  图结构多智能体编排，支持条件分支、循环、review、retry、writer fallback。
```

整体结构可以理解为：

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

## 3. AgentLoop 层

AgentLoop 是项目最早实现的通用 agent harness。

它的核心流程是：

```text
User Goal
  ↓
AgentState
  ↓
LLMAgentPolicy 决定下一步 action
  ↓
如果是 tool_call：
      ToolRuntime 执行工具
      得到 Observation
      写入 AgentStep 和 TraceStore
      回到下一轮
  ↓
如果是 final_answer：
      保存最终答案
      结束
```

相关文件包括：

```text
src/research_pilot/core/agent_loop.py
src/research_pilot/core/state.py
src/research_pilot/core/action.py
src/research_pilot/core/observation.py
src/research_pilot/core/tool_runtime.py
src/research_pilot/core/trace.py
src/research_pilot/agents/llm_agent.py
```

AgentLoop 的优点是灵活，可以让 LLM 自主决定调用哪些工具。缺点是 token 消耗较大，且流程不稳定。比如每一步都需要模型重新阅读 system prompt、tool specs 和当前状态，再决定下一步 action。

因此，后续项目逐渐引入了 workflow 和 graph workflow。

---

## 4. ToolRuntime 与 Tools

ToolRuntime 是项目的工具执行层。AgentLoop 或 workflow 不直接执行具体能力，而是通过 ToolRuntime 调用工具。

典型工具包括：

```text
code_map
code_search
code_read
write_code_answer

paper_search
paper_download
engineered_rag_index
engineered_rag_search
write_evidence_answer

save_report
save_note
```

工具的职责是完成具体动作，例如：

```text
code_search：搜索代码库中的相关文件或片段
paper_download：从 arXiv 下载论文 PDF
engineered_rag_index：将论文同步到 RAG 索引
engineered_rag_search：从本地论文索引中检索证据
write_evidence_answer：基于证据生成回答
```

工具一般不负责复杂规划。复杂流程由 AgentLoop、workflow 或 graph workflow 负责。

---

## 5. Deterministic Workflow 层

随着项目复杂度提高，完全依赖 AgentLoop 自由选择工具会带来不稳定问题。因此 ResearchPilot 增加了确定性 workflow。

Workflow 的核心思想是：

```text
对于高频、结构稳定的任务，不让 LLM 每一步自由选择工具，而是由 Python 显式编排工具调用顺序。
```

这样可以降低 token 消耗，提高稳定性，也方便 evaluation。

---

## 6. CodeWorkflowRunner

CodeWorkflowRunner 负责代码库问答。

典型流程是：

```text
用户代码问题
  ↓
code_map
  ↓
code_search
  ↓
code_read
  ↓
write_code_answer
  ↓
final answer
```

它主要用于回答：

```text
某个类怎么实现？
某个 workflow 的调用链是什么？
某个函数在哪里？
某个报错可能和哪些代码有关？
```

CodeWorkflowRunner 不依赖 AgentLoop 的自由工具选择，而是按稳定路径执行代码理解任务。

---

## 7. PaperWorkflowRunner

PaperWorkflowRunner 是论文研究能力的核心。

它包含三种主要工作流：

### 7.1 paper_answer

用于“只基于已有本地论文索引回答”。

流程：

```text
engineered_rag_search
  ↓
write_evidence_answer
  ↓
final answer
```

适合用户明确要求：

```text
基于已有论文证据回答
只用本地论文
不要下载新论文
```

### 7.2 paper_collect

用于“搜索并下载论文”。

流程：

```text
paper_search
  ↓
paper_download
  ↓
engineered_rag_index
  ↓
save_note
```

适合只想收集论文、更新论文库的任务。

### 7.3 paper_research

这是完整的 adaptive paper research workflow。

流程：

```text
local engineered_rag_search
  ↓
evidence sufficiency check
  ↓
如果证据不足或用户强制搜索：
      paper_download
      engineered_rag_index
      engineered_rag_search
  ↓
write_evidence_answer
  ↓
如果 writer 判断证据不足：
      再次触发 download / index / search / answer
  ↓
save_report
```

这是项目最重要的论文研究链路。它恢复了早期 deep research 的能力：

```text
先查本地；
本地不足则搜索和下载论文；
重建索引；
重新检索；
基于证据生成回答。
```

---

## 8. Graph Workflow Runtime

为了避免 multi-agent 逻辑变成大量 if/else，项目实现了一个轻量级 GraphWorkflowRuntime。

相关文件包括：

```text
src/research_pilot/graph/graph_state.py
src/research_pilot/graph/graph_node.py
src/research_pilot/graph/graph_runner.py
```

GraphWorkflowRuntime 支持：

```text
节点 node
默认边 edge
条件边 conditional edge
状态循环 loop
max_steps 防死循环
visited_nodes 记录路径
GraphState 共享状态
```

它的目标类似 LangGraph 的核心思想，但实现更轻量，更适合作为学习型项目。

---

## 9. Multi-agent Graph Workflow

当前主线 multi-agent 入口默认使用 graph workflow。

典型流程是：

```text
prepare
  ↓
planner
  ↓
code / paper / general
  ↓
reviewer
  ↓
如果通过：final
  ↓
如果不通过：retry 或 writer
  ↓
final
```

相关文件：

```text
src/research_pilot/workflows/multiagent_graph_workflows.py
src/research_pilot/multiagent/blackboard.py
src/research_pilot/multiagent/base_subagent.py
src/research_pilot/multiagent/subagents/
```

---

## 10. Blackboard 黑板机制

ResearchPilot 使用 blackboard-style multi-agent 架构。

也就是说，不同 subagent 不直接共享完整 message history，而是通过一个共享黑板交换信息。

Blackboard 里保存：

```text
user_request
session_summary
recent_messages
recent_turn_memories
code_files
code_search_queries
evidence_sources
report_paths
notes
metadata
```

这种设计的优点是：

```text
所有 agent 可以看到共享任务状态；
trace report 容易生成；
debug 方便；
workflow 状态清晰。
```

不足是：

```text
还没有做到完全的 subagent message isolation；
不同 subagent 仍可能被 blackboard 中的历史信息影响；
后续可以做 filtered context view。
```

---

## 11. SubAgent 设计

项目中的 subagent 是 graph workflow 中的角色节点，不等同于底层 tools。

区别是：

```text
Tool：
  负责具体动作，例如搜索代码、下载论文、读取文件。

SubAgent：
  负责一个角色任务，例如规划、代码问答、论文研究、审查、重写。
```

当前主要 subagent 包括：

```text
PlannerSubAgent
CodeSubAgent
PaperSubAgent
GeneralSubAgent
ReviewerSubAgent
WriterSubAgent
```

---

## 12. PlannerSubAgent

PlannerSubAgent 负责判断用户请求应该交给哪个 specialist。

典型路由：

```text
代码实现、函数、类、报错、调用链
  → CodeSubAgent

论文、文献、综述、调研、找论文、下载论文
  → PaperSubAgent

普通概念解释或无法明确分类的问题
  → GeneralSubAgent
```

Planner 不负责完成任务，只负责路由和改写任务。

---

## 13. CodeSubAgent

CodeSubAgent 不是重新实现代码检索，而是包装 CodeWorkflowRunner。

结构是：

```text
CodeSubAgent
  ↓
CodeWorkflowRunner
  ↓
code_map / code_search / code_read / write_code_answer
```

它把代码任务接入 multi-agent graph。

---

## 14. PaperSubAgent

PaperSubAgent 包装 PaperWorkflowRunner，并保留完整的 adaptive paper research 能力。

它内部会根据用户意图选择：

```text
local_answer：
  明确只用已有论文证据时调用 paper_answer

collect：
  只要求下载或收集论文时调用 paper_collect

adaptive_research：
  默认调用 paper_research
```

当前推荐设计是：

```text
只要是论文相关问题，默认交给 PaperSubAgent；
PaperSubAgent 内部再决定本地回答还是完整研究流程。
```

这样 Planner 不需要精准区分 paper_answer 和 deep_research，降低路由错误风险。

---

## 15. GeneralSubAgent

GeneralSubAgent 负责普通问题兜底。

它可以调用原始 AgentLoop，也可以在必要时调用直接 LLM fallback。

它的作用是防止 graph workflow 对非代码、非论文问题直接失败。

例如：

```text
DetectGPT 是啥？
Agent 是什么？
RAG 和 Agent 的区别是什么？
```

如果这些问题没有明确要求论文调研，就可以由 GeneralSubAgent 处理。

---

## 16. ReviewerSubAgent

ReviewerSubAgent 负责审查候选答案。

它会检查：

```text
是否回答了用户问题
是否有明显 unsupported claim
是否证据不足
是否需要重试
是否需要 writer 改写
```

Reviewer 不直接生成最终答案，而是输出结构化 review result。

---

## 17. WriterSubAgent

WriterSubAgent 用于在 reviewer 判断答案不合格时，对候选答案进行修订。

它接收：

```text
user_request
candidate_answer
review_result
blackboard context
```

然后生成更稳妥的 final answer。

---

## 18. Conversation Memory

ResearchPilot 支持持久化多轮对话。

相关文件：

```text
src/research_pilot/conversation/session.py
src/research_pilot/conversation/session_store.py
src/research_pilot/conversation/conversation_context.py
src/research_pilot/conversation/summarizer.py
src/research_pilot/conversation/turn_memory.py
```

它支持：

```text
session 持久化
recent messages
session summary
turn memory
code files carryover
evidence sources carryover
report paths carryover
```

在 graph multi-agent chat 中，当前用户消息直接作为 `user_request` 传给 graph runner，而 session 作为历史上下文进入 blackboard。这样可以避免把历史上下文和当前问题混在一起，污染路由判断。

---

## 19. Evidence Store 与 Trace Store

项目中每次工具调用都会生成 Observation，并可以写入 AgentStep 和 TraceStore。

Trace 记录包括：

```text
每一步 action
tool input
observation
final answer
run state
```

EvidenceStore 用来保存：

```text
代码证据
论文搜索结果
论文下载结果
RAG evidence blocks
报告路径
```

这些信息不仅用于回答，也用于 debug、turn memory 和 trace report。

---

## 20. MultiAgent Trace Report

项目支持保存 multi-agent trace report。

Trace report 可以展示：

```text
用户请求
最终答案
graph visited path
每个 graph step
planner decision
specialist output
reviewer result
retry 路径
writer output
blackboard summary
metadata preview
```

这使项目具备很强的可解释性和可复盘能力。

---

## 21. Evaluation

项目包含多类 evaluation：

```text
eval-code
eval-paper
eval-multi-agent
```

Evaluation 的作用是检查：

```text
是否走对 workflow
是否包含关键术语
是否返回足够长度的答案
是否保留 metadata
是否有 reviewer output
是否有 graph visited nodes
```

这让项目从“能跑”变成“能回归测试”。

---

## 22. 当前推荐命令

常用命令：

```text
research-pilot chat --multi-agent
research-pilot chat --multi-agent --show-graph --show-plan
research-pilot multi-agent "..."
research-pilot code-answer "..."
research-pilot paper-answer "..."
research-pilot paper-research "..."
research-pilot eval-code
research-pilot eval-paper
research-pilot eval-multi-agent
```

推荐主 demo：

```text
research-pilot chat --multi-agent --show-graph --show-plan --verbose
```

这样可以展示 graph 路径、planner 决策和 workflow 执行细节。

---

## 23. 设计权衡

### AgentLoop

优点：

```text
灵活
开放式
可以自主选择工具
适合探索型任务
```

缺点：

```text
token 消耗高
稳定性较差
不容易评估
容易乱选工具
```

### Deterministic Workflow

优点：

```text
稳定
token 更省
路径可控
便于测试
```

缺点：

```text
自由度较低
需要手写流程
新增任务需要新增 workflow
```

### Graph Workflow

优点：

```text
支持条件分支
支持循环和 retry
适合多智能体协作
trace 清晰
```

缺点：

```text
路由规则需要维护
blackboard 可能带来上下文污染
graph 越复杂越需要文档和 evaluation
```

---

## 24. 当前已解决的关键问题

项目开发中解决了几个重要问题：

```text
1. 从自由 AgentLoop 迁移到 workflow 后，恢复了 deep research 能力。
2. 修复了 PaperSubAgent 默认走 paper_answer 导致只查本地的问题。
3. 修复了 paper_research 中 search query 被长 prompt 污染的问题。
4. 区分了 answer_question 和 search_query。
5. 增加了 evidence insufficiency fallback。
6. 将 graph multi-agent 作为默认主线。
```

这些问题体现了真实 agent 系统中常见的工程挑战：

```text
top-k RAG 不等于证据充分；
workflow 需要反馈闭环；
不同 agent 需要清晰边界；
query rewriting 对搜索质量非常重要；
trace 和 debug 是复杂 agent 的必要组成。
```

---

## 25. 已知限制

当前项目仍有一些可以继续改进的地方：

```text
1. subagent 还没有完整 message isolation。
2. paper search 目前主要依赖 arXiv API。
3. paper candidate ranking 还可以更强。
4. indexing 是同步执行。
5. incremental indexing 仍需进一步优化。
6. fast search answer 和 full RAG answer 还没有分离。
7. reviewer 只能做启发式审查，不是形式化正确性保证。
```

---

## 26. 后续可扩展方向

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

其中最值得做的是：

```text
1. 子 agent 上下文隔离
2. 增量索引
3. 搜索结果直接快速回答
4. 论文候选 rerank
```

---

## 27. 项目总结

ResearchPilot 当前是一个完整的 Agent Engineering 项目。

它包含：

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

项目最大的价值不是单个 RAG 或单个 LLM prompt，而是完整展示了一个 agent 系统从底层运行时到上层多智能体编排的工程实现过程。
