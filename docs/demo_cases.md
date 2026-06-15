# ResearchPilot Demo Cases

本文档整理 ResearchPilot 当前最适合用于项目展示、GitHub 说明和面试讲解的 demo 案例。

推荐展示顺序：

```text
Demo 1：代码库问答
Demo 2：论文研究
Demo 3：多轮对话记忆
Demo 4：Graph Multi-agent Trace
Demo 5：Evaluation
```

这些 demo 的目标不是展示“模型能不能回答问题”，而是展示 ResearchPilot 作为一个完整 Agent Engineering 项目的工程能力：

```text
AgentLoop
ToolRuntime
Workflow
GraphWorkflowRuntime
Blackboard
SubAgent
Conversation Memory
Adaptive Paper Research
Trace Report
Evaluation
```

---

## Demo 1：代码库问答 Codebase QA

### 目标

展示 ResearchPilot 可以理解自己的代码库，并基于代码搜索、文件读取和 evidence-aware answer 生成答案。

### 推荐命令

```powershell
research-pilot chat --multi-agent --show-graph --show-plan --verbose
```

### 推荐输入

```text
AgentLoop 是怎么实现的？
```

### 预期 graph 路径

```text
prepare → planner → code → reviewer → final
```

### 预期能力展示

这个 demo 可以展示：

```text
1. PlannerSubAgent 能识别这是代码问题。
2. CodeSubAgent 会调用 CodeWorkflowRunner。
3. CodeWorkflowRunner 会执行 code_map / code_search / code_read。
4. 最终答案不是纯模型猜测，而是基于代码证据生成。
5. reviewer 会对答案进行审查。
6. graph path 和 tool trace 可见。
```

### 面试讲解要点

可以这样讲：

```text
这个 demo 展示的是代码理解 workflow。系统不是直接让 LLM 回答，而是先由 PlannerSubAgent 判断这是一个 code task，然后路由到 CodeSubAgent。CodeSubAgent 内部调用确定性的 CodeWorkflowRunner，按 code_map、code_search、code_read、write_code_answer 的顺序执行。这样可以避免 LLM 随机选工具，也能让执行过程更稳定、可解释、可评估。
```

---

## Demo 2：论文研究 Adaptive Paper Research

### 目标

展示 ResearchPilot 可以对论文相关问题执行 adaptive paper research：先查本地 RAG，证据不足时搜索、下载、索引新论文，再重新检索并生成证据型答案。

### 推荐命令

```powershell
research-pilot chat --multi-agent --show-graph --show-plan --verbose
```

### 推荐输入

```text
搜索一下并告诉我 AdaDetectGPT 是啥
```

### 预期 graph 路径

```text
prepare → planner → paper → reviewer → final
```

### 预期 paper workflow 路径

```text
PaperSubAgent
  ↓
paper_research
  ↓
paper_download
  ↓
engineered_rag_index
  ↓
engineered_rag_search
  ↓
write_evidence_answer
```

### 预期日志重点

运行过程中应该能看到类似：

```text
PaperSubAgent mode selected: adaptive_research
PaperSubAgent search query: AdaDetectGPT adaptive DetectGPT AI-generated text detection
PaperSubAgent calls paper_research(force_download=True)
Step 1: tool_call -> paper_download
Step 2: tool_call -> engineered_rag_index
Step 3: tool_call -> engineered_rag_search
Step 4: tool_call -> write_evidence_answer
```

### 预期能力展示

这个 demo 可以展示：

```text
1. PlannerSubAgent 能识别这是论文/研究问题。
2. PaperSubAgent 不只是调用本地 RAG，而是调用完整 paper_research。
3. 用户明确说“搜索一下”时，系统会 force_download。
4. 系统会区分 answer_question 和 search_query，避免长 prompt 污染 arXiv 搜索。
5. 下载论文后会进入 RAG index。
6. 最终基于 indexed evidence 生成答案。
```

### 面试讲解要点

可以这样讲：

```text
这个 demo 是项目中最核心的 adaptive paper research。普通 RAG 只是 top-k retrieve 然后回答，但 top-k 返回结果不代表证据真的充分。所以我在 PaperWorkflowRunner 中加入了 evidence sufficiency check 和 post-answer fallback。如果本地证据不足，或者用户明确要求搜索，系统会自动下载论文、更新索引、重新检索并生成证据型答案。
```

---

## Demo 3：本地论文问答 Local Paper Answer

### 目标

展示 ResearchPilot 也支持只基于已有本地论文库回答，而不是每次都联网或下载。

### 推荐命令

```powershell
research-pilot chat --multi-agent --show-graph --show-plan --verbose
```

### 推荐输入

```text
基于已有论文证据，agentic RAG 的架构是什么？
```

### 预期 graph 路径

```text
prepare → planner → paper → reviewer → final
```

### 预期 paper workflow 路径

```text
PaperSubAgent
  ↓
paper_answer
  ↓
engineered_rag_search
  ↓
write_evidence_answer
```

### 预期能力展示

这个 demo 可以展示：

```text
1. PaperSubAgent 能区分 local_answer 和 adaptive_research。
2. 明确说“基于已有论文证据”时，不会下载新论文。
3. 系统可以复用已有 RAG index。
4. 适合展示本地知识库问答能力。
```

### 面试讲解要点

可以这样讲：

```text
PaperSubAgent 不是固定只做一种流程，而是根据用户意图选择 paper_answer、paper_collect 或 paper_research。比如用户明确要求只基于已有论文证据时，系统会走 local_answer，不会下载新论文。这体现了 workflow mode control。
```

---

## Demo 4：普通问题兜底 General SubAgent

### 目标

展示 ResearchPilot 不只处理代码和论文，也能对普通问题进行兜底回答。

### 推荐命令

```powershell
research-pilot chat --multi-agent --show-graph --show-plan
```

### 推荐输入

```text
RAG 和 Agent 的区别是什么？
```

### 预期 graph 路径

```text
prepare → planner → general → final
```

### 预期能力展示

这个 demo 可以展示：

```text
1. PlannerSubAgent 不会把所有问题都错误路由到 code 或 paper。
2. GeneralSubAgent 可以处理普通概念解释。
3. Graph workflow 有兜底路径。
```

### 面试讲解要点

可以这样讲：

```text
这个 demo 展示的是 graph workflow 的兜底能力。如果问题不是代码问题，也不是明确的论文研究问题，PlannerSubAgent 会把它交给 GeneralSubAgent，而不是强行调用 RAG 或 paper workflow。这样可以降低错误工具调用的概率。
```

---

## Demo 5：多轮对话记忆 Conversation Memory

### 目标

展示 ResearchPilot 支持 session memory、recent messages、summary 和 turn memory。

### 推荐命令

```powershell
research-pilot chat --multi-agent --show-graph --show-plan
```

### 推荐对话

第一轮：

```text
AgentLoop 是怎么实现的？
```

第二轮：

```text
那它和现在的 GraphWorkflowRuntime 有什么区别？
```

第三轮：

```text
你结合刚才的解释总结一下这个项目的架构演进。
```

### 预期能力展示

这个 demo 可以展示：

```text
1. 系统能保留多轮上下文。
2. 第二轮中的“它”可以结合上一轮理解。
3. session summary 和 recent messages 可以进入 blackboard。
4. graph multi-agent chat 不会直接把完整 contextual_input 当当前问题，避免污染 planner。
```

### 面试讲解要点

可以这样讲：

```text
这个 demo 展示的是 conversation memory。系统会保存 session、recent messages、summary 和 turn memory。在 graph multi-agent 模式下，我把当前用户消息和历史上下文分开处理：当前消息作为 user_request，历史信息通过 session 进入 blackboard。这样可以让 Planner 判断当前意图时不被长历史污染。
```

---

## Demo 6：Trace Report

### 目标

展示 ResearchPilot 的可解释性和可调试性。

### 推荐命令

```powershell
research-pilot chat --multi-agent --show-graph --show-plan --show-review --save-trace-report --verbose
```

### 推荐输入

```text
搜索一下并告诉我 AdaDetectGPT 是啥
```

### 预期产物

运行后会保存 trace report。

Trace report 中应包含：

```text
user request
final answer
graph visited path
planner decision
specialist output
reviewer result
blackboard summary
metadata preview
```

### 预期能力展示

这个 demo 可以展示：

```text
1. ResearchPilot 的执行过程不是黑箱。
2. 可以看到 planner 怎么决策。
3. 可以看到 specialist 输出。
4. 可以看到 reviewer 结果。
5. 可以看到 graph path。
6. 出错时可以通过 trace report 定位问题。
```

### 面试讲解要点

可以这样讲：

```text
复杂 agent 系统最重要的问题之一是 debug。ResearchPilot 中每个 workflow step 都会记录 action、tool input、observation 和 metadata。multi-agent graph 还会记录 visited nodes、planner decision 和 reviewer result。这样可以在出错时快速定位是 planner 路由错、tool 输入错、检索证据不足，还是 writer 生成问题。
```

---

## Demo 7：Evaluation

### 目标

展示 ResearchPilot 不只是能跑，还有回归测试。

### 推荐命令

```powershell
research-pilot eval-code
```

```powershell
research-pilot eval-paper
```

```powershell
research-pilot eval-multi-agent
```

### 预期能力展示

Evaluation 可以检查：

```text
1. workflow 是否执行成功。
2. final answer 是否包含关键术语。
3. graph visited nodes 是否存在。
4. planner 是否路由到正确 specialist。
5. reviewer 是否运行。
6. metadata 是否保留。
```

### 面试讲解要点

可以这样讲：

```text
Agent 项目不能只靠手动测试。我给 ResearchPilot 增加了 evaluation cases，用来检查代码问答、论文问答和多智能体 workflow 的关键行为。这样在修改 routing、workflow 或 tool input 时，可以快速发现回归问题。
```

---

## 推荐展示顺序

面试或录屏时，推荐按这个顺序展示：

```text
1. README 简要介绍项目
2. 展示项目目录结构
3. 跑 Demo 1：代码库问答
4. 跑 Demo 2：论文研究
5. 展示 trace report
6. 跑 eval-multi-agent
7. 总结架构亮点和可扩展方向
```

---

## 项目讲解主线

可以按下面逻辑讲 ResearchPilot：

```text
最开始我实现了一个通用 AgentLoop，支持 LLM 自由选择工具。
后来发现自由 AgentLoop 对稳定任务不够可靠，而且 token 成本较高。
所以我把代码问答和论文研究抽象成 deterministic workflow。
再往后，为了支持 planner、specialist、reviewer、writer 这种多智能体协作，我实现了一个轻量级 GraphWorkflowRuntime。
现在的主线是 graph-based multi-agent workflow：planner 负责路由，specialist 负责执行任务，reviewer 负责审查，writer 负责兜底改写。
```

---

## 简历项目亮点对应关系

| 项目能力                 | 简历关键词                        |
| -------------------- | ---------------------------- |
| AgentLoop            | custom agent runtime         |
| ToolRuntime          | tool calling infrastructure  |
| CodeWorkflowRunner   | codebase QA                  |
| PaperWorkflowRunner  | adaptive paper research      |
| GraphWorkflowRuntime | graph-based orchestration    |
| Blackboard           | multi-agent shared state     |
| ReviewerSubAgent     | answer verification          |
| Trace Report         | observability / debugging    |
| Evaluation           | regression testing           |
| Conversation Memory  | persistent multi-turn memory |

---

## 当前最推荐的 3 个展示案例

最终简历展示和面试中，最推荐准备这 3 个：

### 1. Codebase QA

```text
AgentLoop 是怎么实现的？
```

展示代码理解、workflow 和 evidence-based answer。

### 2. Adaptive Paper Research

```text
搜索一下并告诉我 AdaDetectGPT 是啥
```

展示 paper search、download、index、RAG、evidence answer。

### 3. Trace Report

```text
保存并展示一次 graph multi-agent trace report。
```

展示可解释性、debug 能力和工程完整度。
