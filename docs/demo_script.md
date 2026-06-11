# ResearchPilot 演示脚本

本文档用于项目演示。你可以按照这里的顺序运行命令，展示 ResearchPilot 的核心能力。

建议演示顺序：

```text
1. 展示项目结构
2. 展示自然语言 ask
3. 展示 paper-answer
4. 展示 paper-collect
5. 展示 paper-research
6. 展示 eval-paper
7. 展示 eval-paper --llm-judge
8. 展示 trace / report / eval output
```

---

## 1. 演示前准备

进入项目根目录：

```bash
cd C:\Users\22168\Desktop\Working\ResearchPilot
```

激活环境：

```bash
conda activate research-pilot
```

确认命令可用：

```bash
research-pilot --help
```

确认环境变量已经配置：

```text
.env
```

至少需要：

```env
OPENAI_API_KEY=...
OPENAI_BASE_URL=...
OPENAI_MODEL=...

PAPER_RAG_ASSISTANT_ROOT=C:\Users\22168\Desktop\Working\paper-rag-assistant

DASHSCOPE_API_KEY=...
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
```

不要在演示中展示真实 API key。

---

## 2. 展示项目结构

运行：

```bash
tree /F src\research_pilot
```

或者在 VSCode 中展示目录：

```text
src/research_pilot/
├── agents/
├── core/
├── evaluation/
├── tools/
├── workflows/
├── workers/
├── cli.py
└── config.py
```

讲解重点：

```text
core/ 是 Agent Harness 核心
tools/ 是工具层
workflows/ 是确定性流程
workers/ 用于隔离外部 EngineeredRAG，解决 Chroma 文件锁
evaluation/ 是评价系统
```

可以这样讲：

> 这个项目不是单一 RAG 脚本，而是分成 Agent Runtime、Tool Runtime、Workflow、Evidence Store 和 Evaluation 几层。

---

## 3. 演示 ask 自然语言入口

命令：

```bash
research-pilot ask "What is the architecture of agentic RAG?"
```

预期展示：

```text
Routed intent: paper_answer
Reason: The user asks a question that can be answered from indexed papers.
Step 1: engineered_rag_search
Step 2: write_evidence_answer
Final Answer
```

讲解重点：

```text
用户没有指定工具名
Intent Router 自动判断这是论文问答
底层自动走 paper-answer workflow
```

可以这样讲：

> 早期调试时需要写 Use engineered_rag_search，但现在通过 ask 命令，用户可以自然语言提问，系统自动路由到稳定 workflow。

---

## 4. 演示 paper-answer

命令：

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?"
```

预期输出结构：

```markdown
## Answer

...

## Architecture Breakdown

...

## Explanation

...

## Sources Used

...

## Limitations

...
```

讲解重点：

```text
paper-answer 使用本地 indexed papers
先调用 engineered_rag_search
把检索结果保存为结构化 evidence blocks
再调用 write_evidence_answer 生成带引用答案
```

可以强调：

> 这个流程是确定性的，不依赖 LLM 自己猜工具顺序，因此比 run 模式更稳定。

---

## 5. 演示保存报告

命令：

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?" --save-report
```

预期：

```text
Report saved: workspace/reports/...
```

打开生成的报告：

```bash
explorer workspace\reports
```

讲解重点：

```text
最终答案不仅显示在终端，也可以保存为 Markdown 报告
适合后续整理文献综述或技术总结
```

---

## 6. 演示 paper-collect 下载论文

命令：

```bash
research-pilot paper-collect "agentic RAG architecture" --max-papers 3
```

预期流程：

```text
Step 1: paper_search
Step 2: paper_download
Step 3: engineered_rag_index
Step 4: save_note
```

讲解重点：

```text
paper_search 搜索论文
paper_download 下载论文并去重
engineered_rag_index 同步到外部 paper-rag-assistant 并重建索引
```

可以展示：

```bash
explorer workspace\documents\papers
```

以及外部项目的：

```text
paper-rag-assistant/data/papers
paper-rag-assistant/chroma_db
paper-rag-assistant/paper_catalog_db
```

如果下载过相同论文，可以展示去重结果：

```text
skipped_duplicates
download_index.json
```

---

## 7. 演示 paper-research local-first 流程

命令：

```bash
research-pilot paper-research "What is the architecture of agentic RAG?"
```

预期流程：

```text
先检索本地 indexed papers
如果证据足够，直接回答并保存报告
如果证据不足，下载新论文、重建索引、重新检索、再写答案
```

讲解重点：

```text
这是一个 local-first workflow
优先复用本地文献库
本地证据不足时才补充下载
```

可以进一步演示强制下载：

```bash
research-pilot paper-research "What is the architecture of agentic RAG?" --force-download --max-papers 2
```

讲解重点：

> 这里使用 subprocess worker 执行 EngineeredRAG 的 search/index/answer，避免 Windows 上 Chroma 文件锁问题。

---

## 8. 演示 eval-paper 规则评价

命令：

```bash
research-pilot eval-paper --max-cases 1
```

预期输出：

```text
[Eval] Running case: paper_qa_001
[Eval] paper_qa_001: PASS

Paper Evaluation Summary
Total: 1
Passed: 1
Failed: 0
Pass rate: 100.0%
Results: workspace/eval_runs/...
Summary: workspace/eval_runs/...
```

讲解重点：

```text
规则评价检查：
workflow 是否成功
是否有 tool error
是否包含 Sources Used
是否包含 Limitations
是否有 citation marker
答案长度是否足够
```

打开评价结果：

```bash
explorer workspace\eval_runs
```

---

## 9. 演示 LLM Judge 评价

命令：

```bash
research-pilot eval-paper --max-cases 1 --llm-judge
```

预期输出：

```json
{
  "groundedness": 4,
  "citation_quality": 4,
  "completeness": 4,
  "clarity": 5,
  "hallucination_risk": 4,
  "overall_score": 4.2,
  "verdict": "PASS",
  "strengths": [...],
  "weaknesses": [...],
  "suggestions": [...]
}
```

讲解重点：

```text
规则评价只能检查格式
LLM Judge 可以评价答案是否 grounded、引用是否合理、完整性如何、幻觉风险如何
```

可以这样讲：

> Evaluation Harness 让这个项目不只是能跑，还能持续检查改动是否让答案质量变差。

---

## 10. 演示 Trace

打开：

```bash
explorer workspace\traces
```

展示某次运行的 trace 文件。

讲解重点：

```text
每一步 action 和 observation 都被保存
方便 debug 和复盘
这也是 Agent 系统可解释性的一部分
```

可以说明：

> 如果某次 Agent 调用了错误工具，我可以通过 trace 看到它在哪一步做错了，而不是只看到最终失败。

---

## 11. 推荐完整演示顺序

面试或项目展示时，建议按下面顺序：

### Step 1：一句话介绍

> ResearchPilot 是一个类 Claude Code 的 Agent Harness，用于论文研究和带引用的论文问答。它结合了 Agent Runtime、Tool Runtime、确定性 workflow、外部 EngineeredRAG、Evidence Store 和 Evaluation Harness。

### Step 2：展示 ask

```bash
research-pilot ask "What is the architecture of agentic RAG?"
```

说明自然语言入口和 intent router。

### Step 3：展示 paper-answer

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?"
```

说明 citation-aware answer。

### Step 4：展示 paper-collect

```bash
research-pilot paper-collect "agentic RAG architecture" --max-papers 3
```

说明论文搜索、下载、去重和索引。

### Step 5：展示 paper-research

```bash
research-pilot paper-research "What is the architecture of agentic RAG?"
```

说明 local-first 研究流程。

### Step 6：展示 eval

```bash
research-pilot eval-paper --max-cases 1 --llm-judge
```

说明规则评价和 LLM Judge。

---

## 12. 常见演示问题和解释

### 问题 1：为什么不全部让 LLM 自己调用工具？

回答：

> 因为完全自由的 tool-calling agent 不稳定。它可能选错工具、忘记保存报告、直接读取 PDF、或者压缩掉引用答案。所以我保留了 Agent Mode 用于开放任务，但对论文问答这种高频稳定任务设计了 deterministic workflow。

---

### 问题 2：为什么要接入外部 EngineeredRAG？

回答：

> 我之前已经实现了一个效果更好的 paper-rag-assistant，它包含 paper-level retrieval、dense/BM25 hybrid retrieval 和 cross-encoder reranking。ResearchPilot 不重复造这些检索模块，而是把它当成 external backend，重点做 Agent Harness、workflow、证据管理和 evaluation。

---

### 问题 3：为什么需要 subprocess worker？

回答：

> Windows 上 Chroma 会锁住数据库文件。如果同一进程先 search 再 rebuild index，容易出现 WinError 32。我把 EngineeredRAG 的 search/index/answer 全部放到子进程中执行，子进程退出后文件句柄会自动释放，这样 local-first workflow 更稳定。

---

### 问题 4：Evaluation 有什么用？

回答：

> 它可以持续检查 workflow 是否成功、是否有 tool error、答案是否有 citation 和 Sources Used。LLM Judge 进一步评价 groundedness、citation quality、completeness 和 hallucination risk。这样项目不只是能跑，还能做回归测试。

---

## 13. 演示结束时总结

可以这样总结：

> ResearchPilot 的重点不是单纯做一个 RAG answer，而是构建一个可追踪、可评估、可扩展的 Agent Harness。LLM 负责理解和生成，workflow 负责稳定编排，Evidence Store 负责证据管理，Evaluation Harness 负责质量检查。
