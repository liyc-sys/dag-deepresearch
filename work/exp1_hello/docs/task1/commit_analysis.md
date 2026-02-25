# liyc-sys 提交分析报告

> 仓库: dag-deepresearch
> 分析范围: liyc-sys 的全部3次提交（2026-02-14 至 2026-02-17）

---

## 总览

liyc-sys 共提交3次，涵盖以下演进路线：

```
[ed9499c] 2026-02-14  建立两层DAG深度报告生成框架（骨架）
[03e1efb] 2026-02-15  添加Token追踪、计时埋点和甘特可视化（可观测性）
[0f286a2] 2026-02-17  添加Goal/Path追踪、topic_file支持和参数调优（可追溯性）
```

整体方向：从"框架可运行"→"框架可观测"→"框架可追溯"。

---

## 提交一：建立两层DAG深度报告生成框架

- **Hash**: `ed9499c`
- **日期**: 2026-02-14 20:38
- **变更量**: +665 行，新增7个文件

### 核心设计：两层架构

```
Layer 1 (ReportOrchestrator)
  ├── plan_report(topic)  ——  调用LLM生成章节DAG大纲
  ├── execute_report(outline)  ——  并行执行章节研究
  └── synthesize_report(outline)  ——  合成最终Markdown报告

Layer 2 (SearchAgent，每个章节独立实例)
  └── 在给定查询上执行多步工具调用搜索
```

### 新增文件详解

#### `FlashOAgents/report_dag.py` (122行)

DAG数据结构与调度逻辑：

| 类/枚举 | 职责 |
|---------|------|
| `SectionStatus` | 章节状态枚举：PENDING / READY / IN_PROGRESS / COMPLETED / FAILED |
| `ReportSection` | 单个章节数据：title, description, research_query, depends_on, status, research_result, trajectory |
| `ReportOutline` | 整体报告大纲，包含所有章节 |

关键方法：
- `get_ready_sections()` — 找出所有依赖已完成的PENDING章节，标记为READY
- `all_completed()` — 判断所有章节是否已完成/失败
- `get_completed_context(section_ids, max_chars=2000)` — 提取已完成章节的内容摘要作为下游章节的上下文
- `validate_dag()` — 用DFS白灰黑三色法检测环，同时验证依赖引用合法性

#### `FlashOAgents/report_orchestrator.py` (326行)

`ReportOrchestrator` 核心编排类：

- `plan_report(topic)` — 最多重试3次调用LLM生成outline JSON，用 `json_repair` 兼容非标准JSON输出
- `execute_report(outline)` — 使用 `ThreadPoolExecutor` + `FIRST_COMPLETED` 实现**即时调度**：完成一个章节后立即提交新的就绪章节，充分利用并发
- 重试机制：章节失败后最多重试 `max_section_retries` 次
- 参数：`max_section_steps=20`, `summary_interval=6`, `section_concurrency=5`

#### `FlashOAgents/prompts/report/report_prompts.yaml` (124行)

三类提示模板：
1. `report_planning` — 引导LLM输出结构化JSON大纲（含section_id、depends_on等字段）
2. `section_research` — 带依赖上下文前缀的章节研究提示
3. `report_synthesis` — 将所有章节结果合成最终报告的提示

#### `run_deep_report.py` / `run_deep_report.sh`

CLI入口，支持参数：`--topic`, `--output_report`, `--max_section_steps`, `--summary_interval`, `--section_concurrency`, `--max_section_retries`, `--prompts_type`

---

## 提交二：添加Token追踪、计时埋点和甘特可视化

- **Hash**: `03e1efb`
- **日期**: 2026-02-15 15:01
- **变更量**: +1990行，修改10个文件（其中新增2个大文件）

### 埋点层级

```
全局
└── ChatMessage: input_token_count, output_token_count（线程安全累加）

章节（ReportSection）
├── wall_clock_time
├── total_input_tokens
└── total_output_tokens

步骤（ActionStep / PlanningStep / SummaryStep）
├── input_tokens, output_tokens
├── llm_start_time, llm_end_time, llm_duration
└── (ToolCall) start_time, end_time, duration
```

### 关键变更

**`FlashOAgents/memory.py`**
- `ToolCall` 新增：`start_time`, `end_time`, `duration`
- `ActionStep` 新增：`input_tokens`, `output_tokens`, `llm_start_time`, `llm_end_time`, `llm_duration`
- `PlanningStep` 新增：`start_time`, `end_time`, `duration`, `input_tokens`, `output_tokens`

**`FlashOAgents/agents.py`**
- 在LLM调用前后记录时间戳，将 `usage.prompt_tokens` / `completion_tokens` 存入对应step
- 在工具执行前后记录ToolCall的时间戳

**`visualize_dag.py`** (1132行，新文件)

静态HTML生成器，三个主要视图：
1. **DAG节点图** — 章节依赖关系可视化，节点颜色反映状态，节点内显示token用量
2. **甘特时间线** — 各章节的并行执行时间轴（挂钟时间）
3. **详情面板** — 点击章节节点后展示：研究结果、每步骤的LLM耗时和token消耗

**`test_token_timing.py`** (687行，33个测试用例)

全面覆盖：ToolCall时间字段、ActionStep时间/token字段、PlanningStep/SummaryStep字段、trajectory序列化、ReportSection时间/token聚合、visualize_dag的HTML生成等

**`run_deep_report.py`**
- 报告生成完成后，自动调用 `visualize_dag.py` 生成可视化HTML

---

## 提交三：添加Goal/Path追踪、topic_file支持和参数调优

- **Hash**: `0f286a2`
- **日期**: 2026-02-17 12:47
- **变更量**: +73行，修改9个文件

### Goal/Path 追踪机制

**动机**：为每个工具调用打上"它属于哪个目标（Goal）下的哪条路径（Path）"的标签，实现计划与行动的端到端可追溯。

**数据流**：
```
toolcalling_agent.yaml (提示模板)
  └── 要求LLM在tool_call JSON中输出 "goal" 和 "path" 字段
      └── agents.py: 解析并存入 ToolCall.goal / ToolCall.path
          └── 观测日志中显示: "Results for tool call 'web_search' [Goal 1 / Path 1.1]"
              └── visualize_dag.py: 在详情面板中展示goal/path标签
```

**`FlashOAgents/memory.py`**
```python
class ToolCall:
    goal: str | None = None   # 新增
    path: str | None = None   # 新增
```

**`FlashOAgents/agents.py`**
```python
tool_goal = tool_call.get("goal", "")
tool_path = tool_call.get("path", "")
tool_call_obj = ToolCall(..., goal=tool_goal, path=tool_path)
# 观测日志加上标签
path_label = f" [{tc_obj.goal} / {tc_obj.path}]" if tc_obj.goal else ""
```

**`FlashOAgents/memory.py` — assistant消息增强**
- 原来assistant消息只有"Calling tools: ..."
- 现在如果有 `action_think`（推理文本），会先输出"Reasoning:\n...\n\n"再输出工具调用，为上下文提供更多语义信息

### `--topic_file` 支持

```bash
# 之前
python3 run_deep_report.py --topic "短主题"

# 现在支持长主题从文件读入
python3 run_deep_report.py --topic_file topic/1.txt
```

`topic_file` 优先级高于 `--topic`，两者均未提供时 `parser.error()` 报错。

### 参数调优

| 参数 | 旧默认值 | 新默认值 | 含义 |
|------|---------|---------|------|
| `summary_interval` | 6 | 8 | 每8步做一次内存摘要（减少中间摘要频率） |
| `section_concurrency` | 5 | 10 | 最大并发章节数从5增至10 |
| `max_chars_per_section` | 2000 | 8000 | 依赖上下文截断长度从2K增至8K |

### 新增辅助文件

- `topic/1.txt` — 示例长主题文本
- `开发记录.txt` — 开发笔记（中文）

---

## 三次提交关联图

```
ed9499c (Feb 14) ─── 骨架
  ├── report_dag.py          ← DAG数据结构
  ├── report_orchestrator.py ← 并发编排
  ├── report_prompts.yaml    ← 提示模板
  └── run_deep_report.py     ← CLI入口

03e1efb (Feb 15) ─── 可观测性
  ├── memory.py              ← 埋点字段扩展（时间/token）
  ├── agents.py              ← 时间/token捕获
  ├── visualize_dag.py       ← 甘特图+token可视化 [NEW]
  └── test_token_timing.py   ← 33个单元测试 [NEW]

0f286a2 (Feb 17) ─── 可追溯性
  ├── memory.py              ← goal/path字段
  ├── agents.py              ← goal/path解析与日志
  ├── toolcalling_agent.yaml ← 提示要求LLM输出goal/path
  └── run_deep_report.py     ← --topic_file支持
```

---

## 代码质量评估

| 维度 | 评价 |
|------|------|
| 架构清晰度 | 两层架构（Orchestrator + SearchAgent）职责分明，DAG调度逻辑集中在 `report_dag.py` |
| 并发设计 | 使用 `FIRST_COMPLETED` 实现真正即时调度，优于批次调度 |
| 错误处理 | 章节级别有重试机制，plan_report有3次重试，使用 `json_repair` 兼容LLM输出 |
| 可观测性 | 三层埋点（step级/章节级/全局），甘特图可视化，测试覆盖充分 |
| 可追溯性 | Goal/Path字段将计划节点与工具调用绑定，方便调试执行路径 |
| 测试覆盖 | 33个单测覆盖所有新的时间/token追踪功能 |
| 参数设计 | 默认值经过调整（summary_interval 6→8，concurrency 5→10，context 2K→8K），反映实际使用经验 |
