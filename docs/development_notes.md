# ResearchPilot 开发过程总结

本文档记录 ResearchPilot 从最初 AgentLoop 到 Workflow，再到 Graph Multi-agent Research Assistant 的开发演进过程。

这个文档的目的不是介绍最终功能，而是复盘项目为什么一步步这样设计，以及每个阶段解决了什么问题。

---

## 1. 项目起点：从 AgentLoop 开始

ResearchPilot 最早的目标是学习和实现一个最小可用的 Agent Harness。

最初关注的问题是：

```text
一个 LLM Agent 到底是怎么运行的？
LLM 如何决定调用工具？
工具结果如何返回给模型？
每一步执行过程如何保存？
什么时候结束并生成 final answer？
```

因此项目最早实现了 AgentLoop 相关组件：

```text
AgentLoop
AgentState
AgentAction
Observation
ToolRuntime
TraceStore
LLMAgentPolicy
```

最基础的运行逻辑是：

```text
User Goal
  ↓
AgentState
  ↓
LLM policy 决定下一步 action
  ↓
如果是 tool_call：
      ToolRuntime 执行工具
      得到 Observation
      写入 AgentStep
      保存 Trace
      继续循环
  ↓
如果是 final_answer：
      保存最终答案
      结束
```

这个阶段的重点是理解 Agent 的底层运行机制。

---

## 2. 第一阶段收获：Agent 不只是一次 LLM 调用

通过实现 AgentLoop，我理解到 Agent 和普通 LLM 调用的区别在于：

```text
普通 LLM 调用：
  user input → model → answer

AgentLoop：
  user goal → model decision → tool call → observation → model decision → ... → final answer
```

也就是说，Agent 的核心不是“回答”，而是：

```text
状态管理
工具选择
工具执行
观察结果
循环控制
终止条件
trace 记录
```

这个阶段让我对 tool calling agent 的基本结构有了完整理解。

---

## 3. 引入 ToolRuntime

为了让 AgentLoop 不直接依赖具体工具，项目引入 ToolRuntime。

ToolRuntime 的职责是：

```text
根据 tool_name 找到工具
校验 tool_input
执行工具 run()
捕获异常
返回 Observation
```

这样上层 AgentLoop 或 Workflow 不需要关心工具内部实现。

工具层逐步加入了：

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

这个阶段的主要收获是：

```text
Agent 系统需要统一的工具接口；
否则每个 workflow 都会和具体工具强耦合。
```

---

## 4. 从自由 AgentLoop 到 Deterministic Workflow

在实现基本 AgentLoop 后，我发现纯自由工具调用存在几个问题。

### 4.1 稳定性问题

对于代码问答，理想流程通常是固定的：

```text
先看项目结构
再搜索相关代码
再读取文件
最后基于代码证据回答
```

但如果完全交给 LLM 自由选择工具，可能出现：

```text
漏掉 code_read
过早 final_answer
重复调用无关工具
上下文变长后决策不稳定
```

### 4.2 Token 成本问题

AgentLoop 每一步都要让 LLM 阅读：

```text
system prompt
tool specs
user goal
history steps
observations
state summary
```

这会导致 token 成本比 deterministic workflow 高很多。

### 4.3 Evaluation 困难

自由 AgentLoop 每次路径可能不同，不利于回归测试。

因此项目进入第二阶段：**为稳定任务设计 deterministic workflow**。

---

## 5. CodeWorkflowRunner

第一个确定性 workflow 是 CodeWorkflowRunner。

它用于代码库问答。

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

这样做的好处是：

```text
流程稳定
token 更省
tool 顺序可控
debug 更容易
evaluation 更容易
```

CodeWorkflowRunner 的出现标志着项目从“自由 AgentLoop demo”开始进入“可控工作流系统”。

---

## 6. PaperWorkflowRunner

随后项目实现了 PaperWorkflowRunner，用于论文问答和论文研究。

PaperWorkflowRunner 包含三类模式：

```text
paper_answer：
  只基于已有论文索引回答。

paper_collect：
  搜索和下载论文，并更新索引。

paper_research：
  local-first adaptive paper research。
```

最初 paper workflow 主要解决两个问题：

```text
如何把已有 EngineeredRAG 接入 Agent 系统？
如何让论文研究不只是一次 RAG search，而是包含搜索、下载、索引、检索和生成？
```

---

## 7. Adaptive Paper Research 的形成

在调试论文研究功能时，逐渐发现普通 RAG 有一个核心问题：

```text
RAG 检索器总会返回 top-k chunks；
即使没有真正相关的信息，也会返回最相近的若干条。
```

所以：

```text
返回 10 条 evidence ≠ 证据充分
```

这导致早期 workflow 会误判：

```text
engineered_rag_search 返回多个 chunks
  ↓
_evidence_is_sufficient 判断数量够
  ↓
write_evidence_answer
  ↓
writer 说证据不足
  ↓
workflow 结束，没有回退
```

后来修复为：

```text
local engineered_rag_search
  ↓
evidence sufficiency check
  ↓
如果证据不足：
      paper_download
      engineered_rag_index
      engineered_rag_search
  ↓
write_evidence_answer
  ↓
如果 writer 仍然说证据不足：
      post-answer fallback
      再次 download / index / search / answer
```

这个阶段的核心收获是：

```text
Agentic RAG 不能只依赖 top-k retrieval；
必须有证据充分性判断和失败回退机制。
```

---

## 8. Query Pollution 问题

在调试 AdaDetectGPT 论文搜索时，发现 arXiv 下载结果非常差，下载了完全不相关的论文。

原因是：

```text
把完整的 answer question 当成 paper search query 传给了 paper_download。
```

当时的 query 类似：

```text
Original user request:
搜索一下并告诉我 AdaDetectGPT 是啥

Planner rewritten request:
搜索并解释 AdaDetectGPT 是什么

Paper workflow instruction:
Use the paper workflow to answer the request...
```

这类长 prompt 会污染 arXiv 搜索，导致搜索引擎匹配到 workflow、tools、dataset 等无关词。

最终修复方式是区分：

```text
answer_question：
  给 write_evidence_answer 使用，可以保留完整用户请求和回答要求。

search_query：
  给 paper_search / paper_download 使用，必须短、干净、关键词化。
```

例如：

```text
answer_question:
  搜索一下并告诉我 AdaDetectGPT 是啥

search_query:
  AdaDetectGPT adaptive DetectGPT AI-generated text detection
```

这个问题说明：

```text
Agent 系统里同一个用户请求在不同工具中需要不同表示；
不能把完整 prompt 直接传给所有工具。
```

---

## 9. 从 Workflow 到 Multi-agent

当 CodeWorkflow 和 PaperWorkflow 都逐渐稳定后，项目进入多智能体阶段。

最初的问题是：

```text
一个系统里既有代码问题、论文问题、普通问题，应该怎么自动分派？
```

于是引入了 SubAgent：

```text
PlannerSubAgent
CodeSubAgent
PaperSubAgent
GeneralSubAgent
ReviewerSubAgent
WriterSubAgent
```

其中：

```text
PlannerSubAgent：
  判断任务类型和路由。

CodeSubAgent：
  包装 CodeWorkflowRunner。

PaperSubAgent：
  包装 PaperWorkflowRunner。

GeneralSubAgent：
  普通问题兜底。

ReviewerSubAgent：
  审查候选答案。

WriterSubAgent：
  根据 reviewer 反馈重写答案。
```

这个阶段的关键设计是：

```text
SubAgent 不直接替代工具；
SubAgent 是 graph workflow 中的角色节点；
具体能力仍然复用已有 workflow 和 tools。
```

---

## 10. Blackboard 共享状态

多智能体之间需要交换信息，因此引入 Blackboard。

Blackboard 保存：

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

选择 blackboard 的原因是：

```text
简单
可调试
trace 容易生成
多个 subagent 可以共享任务状态
```

但它也有不足：

```text
没有完全 message isolation；
不同 subagent 可能受到共享上下文污染；
后续可以做 filtered context view。
```

这个阶段的主要收获是：

```text
多智能体系统最难的不是“有多个 agent”，而是如何管理共享状态和上下文边界。
```

---

## 11. GraphWorkflowRuntime

当 multi-agent 逻辑越来越复杂时，简单 if/else 已经不够清晰。

因此项目实现了轻量级 GraphWorkflowRuntime。

它支持：

```text
GraphState
GraphNode
FunctionGraphNode
default edge
conditional edge
visited nodes
step records
max_steps
final answer
```

当前 multi-agent graph 路径是：

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

Graph workflow 的价值是：

```text
把复杂控制流显式表达成节点和边；
让执行路径可记录；
让 retry 和 reviewer fallback 更自然；
方便后续扩展更多 specialist。
```

这个阶段后，ResearchPilot 的主线从普通 workflow 变成了 graph-based multi-agent workflow。

---

## 12. Conversation Memory

为了支持多轮对话，项目引入 Conversation Memory。

包括：

```text
session store
recent messages
session summary
turn memory
evidence carryover
report path carryover
```

一个重要修复是：

```text
graph multi-agent chat 中，当前用户消息应该直接作为 user_request；
历史上下文通过 session 进入 blackboard；
不要把 contextual_input 作为当前 user_request。
```

原因是：

```text
如果把历史上下文和当前问题拼成一个长输入传给 planner，
planner 可能被历史信息污染，
从而错误判断当前问题类型。
```

这个阶段的收获是：

```text
多轮记忆不能简单拼接；
当前意图和历史上下文应该分开建模。
```

---

## 13. Trace Report

随着系统越来越复杂，debug 变得非常重要。

因此项目加入 multi-agent trace report。

Trace report 包含：

```text
user request
final answer
graph visited path
step records
planner decision
specialist output
reviewer result
retry path
writer output
blackboard summary
metadata preview
```

实际开发中，trace report 和 verbose log 多次帮助定位问题，例如：

```text
PaperSubAgent 是否走了 paper_answer 还是 paper_research？
paper_download 收到的 query 是 search_query 还是长 prompt？
reviewer 是否触发？
graph path 是否走到 expected specialist？
```

这个阶段的收获是：

```text
复杂 Agent 系统必须可观察；
没有 trace，很难判断问题出在 planner、tool、workflow、retrieval 还是 writer。
```

---

## 14. Evaluation

为了避免每次修改 workflow 后出现回归问题，项目加入 evaluation。

包括：

```text
eval-code
eval-paper
eval-multi-agent
```

Evaluation 检查：

```text
workflow 是否成功
final answer 是否包含关键术语
graph visited nodes 是否存在
planner 是否路由正确
reviewer 是否运行
metadata 是否保留
```

这不是严格学术 benchmark，而是工程上的 regression testing。

收获是：

```text
Agent 项目不能只靠手动 demo；
需要最小可用 evaluation 来保证后续修改不会破坏主流程。
```

---

## 15. 当前稳定版本

目前 ResearchPilot 已经形成稳定主线：

```text
CLI / chat
  ↓
Graph Multi-agent Runner
  ↓
PlannerSubAgent
  ↓
CodeSubAgent / PaperSubAgent / GeneralSubAgent
  ↓
ReviewerSubAgent
  ↓
Final / Retry / Writer
```

代码问题：

```text
planner → code → CodeWorkflowRunner → code tools → writer
```

论文问题：

```text
planner → paper → PaperWorkflowRunner → paper tools / RAG tools → writer
```

普通问题：

```text
planner → general → AgentLoop or LLM fallback
```

---

## 16. 当前项目价值

ResearchPilot 当前最有价值的点不是某一个单点功能，而是完整的 Agent 系统工程结构：

```text
AgentLoop
ToolRuntime
State / Action / Observation
TraceStore
Deterministic Workflow
GraphWorkflowRuntime
Blackboard Multi-agent
Conversation Memory
Adaptive Paper Research
Codebase QA
Trace Report
Evaluation
```

这体现的能力包括：

```text
理解 Agent 运行机制
理解 tool calling 基础设施
理解 workflow 稳定化
理解 multi-agent orchestration
理解 Agentic RAG 的证据问题
理解 context pollution 和 query pollution
理解 trace / evaluation 对复杂 Agent 的重要性
```

---

## 17. 项目中的关键经验

### 17.1 自由 AgentLoop 不适合所有任务

开放式任务可以用 AgentLoop，但结构稳定任务更适合 deterministic workflow。

### 17.2 RAG top-k 不等于证据充分

检索器永远会返回最相近的 chunks，因此需要 evidence sufficiency check。

### 17.3 搜索 query 和回答 question 必须分离

工具输入不是越完整越好。搜索工具需要短 query，回答工具需要完整上下文。

### 17.4 多轮记忆不能直接拼进当前问题

历史上下文应该作为 context，而不是覆盖当前 user_request。

### 17.5 多智能体系统需要 trace

没有 trace，复杂 agent 出错时很难定位。

### 17.6 Evaluation 是工程稳定性的基础

即使不是严格 benchmark，也要有最小回归测试。

---

## 18. 后续如果继续做，可以怎么做

当前项目已经适合作为简历项目展示。后续可以继续增强：

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

其中优先级最高的是：

```text
1. SubAgent Context Isolation
2. Incremental-only RAG Index
3. Fast Paper Search Answer
4. Paper Candidate Reranking
```

---

## 19. 总结

ResearchPilot 的开发过程可以概括为：

```text
AgentLoop
  ↓
ToolRuntime
  ↓
Code / Paper Tools
  ↓
Deterministic Workflow
  ↓
Paper Adaptive Research
  ↓
Multi-agent SubAgent
  ↓
GraphWorkflowRuntime
  ↓
Conversation Memory
  ↓
Trace Report
  ↓
Evaluation
```

这个过程完整体现了一个 Agent 项目从 demo 到可展示工程系统的演进路径。

最终 ResearchPilot 可以作为一个 LLM Agent / RAG / AI Application Engineer 方向的简历项目，重点展示对 Agent 系统工程的理解和实践能力。
