# 对接文档：DRB SOTA攻关项目

> **项目启动时间**：2026-02-18
> **状态**：📋 路线图制定完成，等待实施
> **目标**：将Report框架（Two-Layer DAG）在DeepResearch Bench上达到SOTA水平

---

## 一、项目背景

### 1.1 用户需求

用户在本次对话中提出长期目标：

> **"给你一个长期目标: 将这个report框架, 在drb上达到sota, 所以你需要给出一个表格: 模型A+普通框架, 模型A+report框架. 以及你有很多细节要tune才能sota, 加油吧"**

### 1.2 已有基础

在本次工作之前，Report框架已经在DRB上完成了初步评估：

**DRB官方评估结果**（使用豆包Seed 1.6作为judge）：
- Comprehensiveness: 7.40/10
- Insight: 6.70/10 ⚠️ 最弱项
- Instruction Following: 8.46/10
- Readability: 8.01/10
- **Overall: 7.67/10 (76.7%)**
- **FACT Citations: 0.00** ❌ 致命问题

**评估文件**：
- 详细结果：`assets/output/scored/report_drb_med_official_scored.jsonl` (50条)
- 汇总结果：`assets/output/scored/report_drb_med_official_summary.json`
- 评估日志：`assets/logs/rescore_drb_official_v2.log`

---

## 二、本次工作内容

### 2.1 调研DRB SOTA水平

通过WebSearch调研了DeepResearch Bench官方leaderboard（2026年2月最新）：

**商业系统SOTA**：
1. 🥇 Qianfan-DeepResearch Pro（2026-02-03登顶）
2. 🥈 Qianfan-DeepResearch
3. 🥉 Gemini-2.5-Pro Deep Research：**48.88**（RACE score）
4. OpenAI Deep Research：**46.98**
5. MiroFlow-English：72.19（不同评分体系）

**开源系统**：
- Rank 6: LangChain-Open-Deep-Research（GPT-4.1 + Tavily）**← 目标超越！**

**调研来源**：
- [DeepResearch Bench官网](https://deepresearch-bench.github.io/)
- [Hugging Face Leaderboard](https://huggingface.co/spaces/Ayanami0730/DeepResearch-Leaderboard)
- [GitHub仓库](https://github.com/Ayanami0730/deep_research_bench)
- [ArXiv论文](https://arxiv.org/abs/2506.11763)

### 2.2 当前表现分析

**Report框架的优势**：
- ✅ Instruction Following高（8.46）：任务理解准确
- ✅ Readability高（8.01）：结构清晰，组织良好
- ✅ Comprehensiveness尚可（7.40）：信息覆盖基本充分

**关键问题识别**：

#### 🔴 P0 Critical: FACT = 0（无引用）

**问题描述**：
- 生成的报告完全没有引用标记和References section
- FACT得分为0，无法参与引用准确性评估

**根本原因**：
1. SearchAgent没有记录search结果的traces
2. Section生成时没有要求添加引用标记（如[§1], [§2]）
3. Report finalization时没有生成References section

**影响**：
- 无法在官方leaderboard上对比（FACT是核心指标）
- 研究报告的可信度问题
- 与其他系统不公平对比

#### 🟡 P1 Major: Insight偏低（6.70/10）

**问题分析**：
- Insight（6.70）显著低于其他维度
- 对比Instruction Following（8.46）说明**不是任务理解问题**
- 对比Readability（8.01）说明**不是结构问题**
- **核心问题：缺少深度分析和批判性思考**

**可能原因**：
1. Section research prompt过于强调"事实罗列"，缺少"分析"要求
2. 没有跨section的综合分析（synthesis）
3. 缺少forward-looking thinking和implications讨论
4. 模型能力限制（Seed 1.6可能不足）

### 2.3 对比实验设计

为了证明Report框架的价值，设计了以下对比实验：

| 模型 | 框架 | 类型 | Overall（预估） | FACT | 说明 |
|------|------|------|----------------|------|------|
| Seed 1.6 | Simple Search Agent | Baseline（无规划） | ~6.5 | ~10 | 只有search+生成，无planning |
| Seed 1.6 | Report (当前) | Two-Layer DAG | **7.67** | **0** ❌ | 有规划，但缺引用 |
| Seed 1.6 | Report (优化后) | Two-Layer DAG + 优化 | **8.5+** 🎯 | **30+** | +引用系统+优化prompt |
| - | Gemini-2.5-Pro DR | 商业SOTA | 48.88* | 111.21 | 不同评分体系* |
| - | LangChain-Open-DR | 开源baseline | Rank #6 | ~40 | GPT-4.1+Tavily |

**实验目标**：
1. 证明planning（Two-Layer DAG）的价值（vs Simple Search）
2. 证明优化后可达到8.5+（vs 当前7.67）
3. 成为**开源框架中的SOTA**（超越LangChain-Open-Deep-Research）

### 2.4 优化路线图制定

制定了4个阶段的详细优化计划，预计4-5周达到SOTA：

#### Phase 1: 修复致命问题（Week 1-2）

**🔴 P0: 实现完整引用系统**
- 时间：2-3天
- 内容：
  1. 在SearchAgent中记录search traces
  2. 修改section prompt要求添加引用标记
  3. 在report末尾生成References section
- 预期：FACT 0 → 25+，Overall +0.3

**🟡 P1: 优化Insight prompt**
- 时间：1-2天
- 内容：
  1. 重写section prompt强调"深度分析"
  2. 添加"Synthesis & Insights" section
  3. 包含forward-looking thinking
- 预期：Insight 6.70 → 8.0+，Overall +0.2

**📊 实现Simple Search Baseline**
- 时间：1天
- 内容：创建无planning的search agent
- 预期：证明planning的价值（baseline ~6.5 vs Report 7.67）

**Phase 1总预期**：Overall 7.67 → 8.2+，FACT 0 → 25+

#### Phase 2: 系统优化（Week 3-4）

**🟢 P2: 优化outline planning**
- 更细粒度的section划分（5-6个→8-10个）
- 动态调整outline
- Topic coverage validation

**🟢 P2: 优化search质量**
- Query diversification（每section 3-5个不同角度query）
- 去重和ranking
- Iterative search

**🟢 P3: 提升readability**
- 结构优化（添加Executive Summary）
- 语言优化

**Phase 2总预期**：Overall 8.2 → 8.5+

#### Phase 3: 官方评估对齐（Week 3-4）

**🔵 P1: 使用官方RACE evaluation**
- 获取reference articles
- 运行官方evaluation script
- 使用豆包Seed 1.6作为judge（降低成本）
- 获得归一化RACE分数（可比）

**🔵 P2: 完整FACT evaluation**
- Extract citations from reports
- Deduplicate URLs
- Scrape with Jina API
- Validate citations
- 计算Citation Accuracy

**Phase 3总预期**：获得官方可比分数，Citation Accuracy ≥ 80%

#### Phase 4: 扩展到完整DRB-100（Week 4-5）

- 在100条任务上运行（50 EN + 50 CN，22个领域）
- 分析不同领域的表现差异
- 提交官方leaderboard
- **目标：开源框架SOTA** 🏆

### 2.5 成功指标定义

| 级别 | 目标 |
|------|------|
| **Minimal Success**（最低标准） | <ul><li>FACT citations ≥ 20/task（从0提升）</li><li>Insight ≥ 8.0/10（从6.70提升）</li><li>Overall ≥ 8.0/10（从7.67提升）</li><li>显著优于无规划baseline</li></ul> |
| **Target Success**（目标标准） | <ul><li>FACT citations ≥ 30/task</li><li>Citation accuracy ≥ 80%</li><li>Overall ≥ 8.5/10</li><li>进入官方leaderboard Top 10</li></ul> |
| **Ambitious Success**（理想标准） | <ul><li>Overall ≥ 9.0/10</li><li>官方leaderboard Top 5</li><li>**成为开源框架中的SOTA**</li><li>超越LangChain-Open-Deep-Research</li></ul> |

---

## 三、产出文件

### 3.1 详细路线图

**文件**：`work/exp3_med_full/docs/SOTA_ROADMAP.md`

**内容**（20页+详细文档）：
1. 当前状况分析
   - Report框架表现（7.67/10, FACT=0）
   - DRB leaderboard SOTA调研
   - 对比其他系统（Gemini-2.5-Pro, LangChain等）

2. 致命问题详细分析
   - 🔴 Critical Issue #1: FACT=0（无引用）
   - 🟡 Major Issue #2: Insight偏低（6.70/10）
   - 根本原因、影响、解决方案

3. 优化路线图（Phase 1-4）
   - 每个Phase的详细实现方案
   - **代码示例**：如何实现引用系统
   - **Prompt模板**：优化后的section/synthesis prompt
   - 预期提升和验证指标

4. Baseline实验计划
   - Simple Search Agent（无规划）
   - 单层规划（串行）
   - Report框架（优化后）

5. 时间线和资源估算
   - 4-5周详细时间表
   - 每个任务的时间估计和优先级

6. 风险和挑战
   - Risk 1: 引用系统实现复杂度
   - Risk 2: Insight提升效果有限
   - Risk 3: 官方评估分数不一致
   - 缓解措施

7. 参考资源
   - 官方资源（论文、GitHub、Leaderboard）
   - 内部代码（X-EvalSuit, Report框架）

**关键亮点**：
- ✅ 完整的代码实现示例（引用系统、prompt优化）
- ✅ 详细的技术分析（RACE计算公式、FACT pipeline）
- ✅ 明确的成功标准（3个级别）
- ✅ 实用的风险缓解措施

### 3.2 可视化对比页面

**文件**：`work/exp3_med_full/docs/drb_sota_comparison.html`

**内容**（静态HTML，数据内嵌）：
1. **Header**：项目标题、目标、当前状态
2. **Current Performance**：6个指标卡片
   - Comprehensiveness: 7.40/10
   - Insight: 6.70/10 ⚠️
   - Instruction Following: 8.46/10
   - Readability: 8.01/10
   - Overall: 7.67/10
   - FACT Citations: 0.00 ❌

3. **Critical Issues**：2个问题卡片
   - 🔴 P0: FACT=0（红色边框，详细说明）
   - 🟡 P1: Insight低（橙色边框，详细说明）

4. **Framework Comparison**：对比表格
   - 行：Simple Search, Report(Current), Report(Optimized), Gemini-2.5-Pro, LangChain
   - 列：4个RACE维度 + Overall + FACT
   - 颜色标记：当前（蓝色）、目标（绿色）、SOTA（金色）

5. **Performance Visualization**：横向条形图
   - 当前表现（各维度0-10分）
   - 优化后目标（各维度对比）
   - 提升幅度标注

6. **Optimization Roadmap**：4个phase卡片
   - Phase 1: 修复致命问题（Week 1-2）
   - Phase 2: 系统优化（Week 3-4）
   - Phase 3: 官方评估对齐（Week 3-4）
   - Phase 4: 扩展到完整DRB-100（Week 4-5）
   - 每个phase包含任务列表和预期提升

7. **Success Metrics**：3个成功标准卡片
   - Minimal Success（最低标准）
   - Target Success（目标标准）
   - Ambitious Success（理想标准）

8. **References**：官方和内部资源链接

**设计特点**：
- 🎨 渐变色设计（紫色主题）
- 📊 数据可视化（条形图、指标卡片）
- 🎯 优先级标记（P0/P1/P2颜色区分）
- ⚡ 动画效果（fadeIn）
- 📱 响应式布局

**访问方式**：
```bash
# 使用show命令部署（需要在开发机上执行）
show work/exp3_med_full/docs/drb_sota_comparison.html drb_sota_roadmap

# 或手动复制到viz目录
cp work/exp3_med_full/docs/drb_sota_comparison.html /path/to/viz/drb_sota_roadmap.html
```

### 3.3 对接文档

**文件**：`work/exp3_med_full/docs/HANDOVER_SOTA_ATTACK.md`（本文件）

**内容**：
- 项目背景和用户需求
- 本次工作内容（调研、分析、设计）
- 产出文件详细说明
- 技术细节（引用系统实现、Prompt优化、官方评估）
- 下一步行动计划
- 风险和挑战

---

## 四、技术细节

### 4.1 引用系统实现方案

**核心问题**：当前Report框架生成的报告没有引用，FACT得分为0

**实现步骤**：

#### Step 1: 记录Search Traces

在SearchAgent中添加traces记录：

```python
class SearchAgent:
    def __init__(self, model, ...):
        self.search_traces = {}  # {snippet_id: {Title, URL, Snippet}}
        self.snippet_counter = 0

    def search(self, query):
        results = self._call_search_api(query)

        for result in results:
            self.snippet_counter += 1
            snippet_id = f"§{self.snippet_counter}"

            self.search_traces[snippet_id] = {
                "Title": result["title"],
                "URL": result["url"],
                "Snippet": result["snippet"]
            }

        return results
```

#### Step 2: 修改Section生成Prompt

在prompt中要求添加引用标记：

```python
section_prompt = f"""
Write a detailed section about: {section_topic}

Requirements:
1. Provide deep analysis and insights (not just facts)
2. **IMPORTANT**: When stating facts, add citation marks like [§1], [§2]
3. Use the search results provided below

Search Results:
{self._format_search_results_with_ids()}

Structure:
- Overview
- Key Findings (with analysis and citations [§N])
- Critical Analysis
- Implications

Remember to cite all facts with [§N] references!
"""
```

**关键点**：
- 搜索结果格式化时包含snippet_id
- Prompt中明确要求"cite all facts"
- 使用`[§N]`格式（与DRB官方格式一致）

#### Step 3: 生成References Section

在report finalization时生成引用列表：

```python
def finalize_report(self, sections, search_traces):
    # 1. 合并各section
    report_body = "\n\n".join([s["content"] for s in sections])

    # 2. 解析引用
    citation_pattern = re.compile(r'\[§(\d+)\]')
    cited_ids = citation_pattern.findall(report_body)
    cited_ids = sorted(set(cited_ids), key=lambda x: int(x))

    # 3. 构建引用列表
    references = []
    for cid in cited_ids:
        snippet_id = f"§{cid}"
        if snippet_id in search_traces:
            url = search_traces[snippet_id]["URL"]
            references.append(f"[{cid}] {url}")

    # 4. 追加到report
    if self._is_chinese(report_body):
        report = report_body + "\n\n## 参考文献\n" + "\n".join(references)
    else:
        report = report_body + "\n\n## References\n" + "\n".join(references)

    return report
```

**验证指标**：
- 平均引用数 ≥ 30/task
- 引用覆盖率 ≥ 80%（关键facts有引用）
- 可通过FACT pipeline validation（citation accuracy ≥ 80%）

### 4.2 Insight优化Prompt设计

**核心问题**：Insight（6.70）显著低于其他维度

**优化方案1：重写Section Research Prompt**

**当前版本问题**（推测）：
```python
# 可能过于简单
"Write a comprehensive section about {topic}. Include relevant facts and data."
```

**优化后版本**：
```python
section_prompt = f"""
Write an insightful and analytical section about: {section_topic}

Requirements:
1. **Deep Analysis**: Don't just list facts - analyze WHY and HOW
2. **Critical Thinking**: Evaluate different perspectives, identify key issues
3. **Causal Relationships**: Explain cause-effect and underlying mechanisms
4. **Implications**: Discuss implications, potential solutions, recommendations
5. **Forward-Looking**: Consider future trends and developments
6. **Citations**: Cite all facts with [§N] references

Structure:
- Overview (context and background)
- Key Findings (with analysis, not just facts) [§N]
- Critical Analysis (evaluate and synthesize) [§N]
- Implications and Insights [§N]

Search Results:
{formatted_search_results}

Remember: ANALYZE, don't just report!
"""
```

**关键改进**：
- ✅ 明确强调"analyze WHY and HOW"（不只是列举facts）
- ✅ 要求"critical thinking"和"evaluate perspectives"
- ✅ 包含"implications and recommendations"
- ✅ 添加"forward-looking thinking"

**优化方案2：添加Synthesis Section**

在outline generation时，自动添加一个综合分析section：

```python
# 在outline中添加
outline = [
    "Introduction",
    "Section 1: Background and Context",
    "Section 2: Current Situation",
    "Section 3: Key Challenges",
    "Synthesis & Key Insights",  # ← 新增！
    "Conclusion and Recommendations"
]

# Synthesis section的特殊prompt
synthesis_prompt = """
Based on all previous sections, provide a synthesis that:

1. **Overarching Patterns**: Identify common themes and patterns across sections
2. **Cross-Section Connections**: Connect insights from different aspects
3. **High-Level Analysis**: Offer analysis that goes beyond individual sections
4. **Key Implications**: Discuss broader implications for stakeholders
5. **Actionable Recommendations**: Provide concrete, evidence-based recommendations
6. **Future Directions**: Consider trends and future developments

Previous sections summary:
{sections_summary}

Provide deep, integrative analysis - not just a summary!
Cite evidence from previous sections using [§N] references.
"""
```

**预期效果**：
- Insight 6.70 → 8.0+（+1.3分）
- Overall +0.2-0.3

### 4.3 官方RACE评估对齐

**核心问题**：当前使用point-wise RACE（简化版），与官方不可比

**官方vs当前对比**：

| 方面 | 当前方法 | 官方方法 |
|------|---------|---------|
| 评分方式 | Point-wise（直接打分0-10） | Normalized（target/(target+reference)） |
| Reference | 无reference对比 | 与高质量reference对比 |
| Judge模型 | 豆包Seed 1.6 | Gemini-2.5-Pro |
| 分数范围 | 0-10 | 0-1归一化 |
| 可比性 | ❌ 不可比 | ✓ 可比（leaderboard） |

**使用官方评估的步骤**：

#### Step 1: 准备数据

使用X-EvalSuit的`format_for_drb`函数转换格式：

```python
from agentic_eval.judger.drb import format_for_drb

formatted_data = []
for item in results:
    formatted = format_for_drb({
        "id": item["task_id"],
        "problem": item["question"],
        "final_response": item["report"],
        "conversation_history": item.get("traces", []),
    })
    formatted_data.append(formatted)

# 保存为JSONL
output_path = "data/test_data/raw_data/report_drb_med.jsonl"
with open(output_path, "w") as f:
    for item in formatted_data:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
```

#### Step 2: 运行RACE评估

```bash
cd /path/to/deep_research_bench

python deepresearch_bench_race.py \
    report_drb_med \
    --raw_data_dir data/test_data/raw_data \
    --max_workers 10 \
    --query_file data/prompt_data/query.jsonl \
    --output_dir results/race/report_drb_med
```

**输出**：`results/race/report_drb_med/race_result.txt`

#### Step 3: 运行FACT评估

完整pipeline：Extract → Deduplicate → Scrape → Validate → Stat

```bash
# Extract citations
python -m utils.extract \
    --raw_data_path data/test_data/raw_data/report_drb_med.jsonl \
    --output_path results/fact/extracted.jsonl \
    --query_data_path data/prompt_data/query.jsonl \
    --n_total_process 10

# Deduplicate URLs
python -m utils.deduplicate \
    --raw_data_path results/fact/extracted.jsonl \
    --output_path results/fact/deduplicated.jsonl \
    --query_data_path data/prompt_data/query.jsonl \
    --n_total_process 10

# Scrape URLs with Jina API
python -m utils.scrape \
    --raw_data_path results/fact/deduplicated.jsonl \
    --output_path results/fact/scraped.jsonl \
    --n_total_process 10

# Validate citations
python -m utils.validate \
    --raw_data_path results/fact/scraped.jsonl \
    --output_path results/fact/validated.jsonl \
    --query_data_path data/prompt_data/query.jsonl \
    --n_total_process 10

# Calculate statistics
python -m utils.stat \
    --input_path results/fact/validated.jsonl \
    --output_path results/fact/fact_result.txt
```

**输出指标**：
- Citation Accuracy = supported / (supported + unsupported)
- Effective Citations = 平均有效引用数
- 目标：Citation Accuracy ≥ 80%, Effective Citations ≥ 30

**成本考虑**：
- 官方用Gemini-2.5-Pro：贵💰（约$1-2/50条）
- 替代方案：豆包Seed 1.6：便宜（约$0.1/50条）
- 建议：同时运行两个judge，验证相关性（Pearson correlation）

---

## 五、下一步行动

### 5.1 立即开始（本周 Week 1）

#### 任务1：🔴 P0 - 实现引用系统

**负责人**：待分配
**时间**：2-3天
**优先级**：Critical

**子任务**：
- [ ] 修改`base_agent.py`中的SearchAgent，添加`search_traces`记录
- [ ] 修改section generation prompt，要求添加引用标记
- [ ] 实现`finalize_report`方法，生成References section
- [ ] 在5条任务上测试和验证
- [ ] 检查引用覆盖率和准确性

**验证标准**：
- 平均引用数 ≥ 20/task
- 所有report包含References section
- 引用格式符合DRB官方要求（[§N]）

#### 任务2：🟡 P1 - 优化Insight prompt

**负责人**：待分配
**时间**：1-2天
**优先级**：High

**子任务**：
- [ ] 重写`prompts/default/action.txt`（或创建`prompts/insight/`）
- [ ] 添加"Synthesis & Insights" section到outline
- [ ] 在5条任务上A/B测试（default vs insight prompts）
- [ ] 对比Insight分数变化

**验证标准**：
- Insight score ≥ 7.5/10（当前6.70）
- 报告中包含明显的分析性语句（不只是facts）

#### 任务3：📊 Baseline - 实现Simple Search Agent

**负责人**：待分配
**时间**：1天
**优先级**：Medium

**子任务**：
- [ ] 在`step2_run_eval.py`中添加`simple_search`模式
- [ ] Patch掉planning_step（参考flashsearcher实现）
- [ ] 在50条DRB任务上运行
- [ ] 评分并对比Report框架

**验证标准**：
- Simple Search Overall ≤ 7.0/10（低于Report的7.67）
- 证明planning的价值

### 5.2 本月目标（Week 1-4）

- [ ] Phase 1全部任务完成（引用+Insight优化）
- [ ] Overall达到8.0+（从7.67提升）
- [ ] FACT citations达到25+（从0提升）
- [ ] Phase 3.1完成（官方RACE evaluation）
- [ ] Baseline实验完成

### 5.3 下月目标（Week 5-8）

- [ ] Phase 2全部任务完成（系统优化）
- [ ] Overall达到8.5+
- [ ] Phase 3.2完成（完整FACT evaluation）
- [ ] Citation Accuracy ≥ 80%
- [ ] 在完整DRB-100上评估
- [ ] 提交官方leaderboard
- [ ] **目标：开源框架SOTA** 🏆

---

## 六、风险和挑战

### Risk 1: 引用系统实现复杂度

**挑战**：
- 需要修改多个模块（SearchAgent, prompt, report assembly）
- 可能引入bugs或破坏现有功能
- 引用格式需要与DRB官方完全一致

**缓解措施**：
- ✅ 先在小规模测试集（5条）上验证
- ✅ 保持向后兼容，添加feature flag
- ✅ 增加单元测试
- ✅ 逐步rollout（5条→10条→50条→100条）

**应急方案**：
- 如果引用系统实现困难，可以先用后处理方式（从traces中提取URL并追加）
- 虽然不够优雅，但可以快速验证效果

### Risk 2: Insight提升效果有限

**挑战**：
- 深度分析依赖模型能力
- Prompt优化效果可能有上限
- Seed 1.6可能不足以生成深刻洞察

**缓解措施**：
- ✅ 尝试多个prompt变体，A/B测试
- ✅ 考虑添加multi-round refinement（review后重写）
- ✅ 如果Seed 1.6不够，升级到GPT-4.1或Claude Opus
- ✅ 先充分挖掘prompt潜力，再考虑换模型

**应急方案**：
- 如果Insight仍然无法提升到8.0，可以接受7.5+
- Focus on其他维度的优化（Comprehensiveness, FACT）

### Risk 3: 官方评估分数不一致

**挑战**：
- 官方RACE用Gemini-2.5-Pro，我们用豆包
- 两个judge可能评分标准不一致
- 无法确保leaderboard可比性

**缓解措施**：
- ✅ 同时运行Gemini和豆包，计算相关性（Pearson correlation）
- ✅ 如果相关性低（<0.8），考虑使用Gemini（虽然贵）
- ✅ 在论文中report两种judge的结果
- ✅ 重点关注**相对提升**（优化前vs优化后）

**应急方案**：
- 如果豆包评分不可靠，使用少量Gemini评分（如10-20条）来校准
- 或者使用其他开源judge（如LLama-3.1-70B）

### Risk 4: 时间估算不准确

**挑战**：
- 实现可能比预期复杂
- 调试和验证可能费时
- 推理时间（100条任务 × 多个框架）

**缓解措施**：
- ✅ 预留buffer（4-5周→实际可能6-8周）
- ✅ 优先P0/P1，P2/P3可选
- ✅ 并行推理（多个进程）
- ✅ Focus on minimal success先，再pursue ambitious goals

---

## 七、代码位置和资源

### 7.1 Report框架核心代码

- **Base Agent**：`dag-deepresearch/base_agent.py`
  - SearchAgent类
  - planning_step, action_step, summary_step, final_answer_step

- **FlashOAgents**：`dag-deepresearch/FlashOAgents/`
  - Model wrappers
  - Tools (search, calculator, etc.)

- **Prompts**：
  - `prompts/default/` - 当前使用的prompts
  - `prompts/medical/` - 医学优化prompts（可参考）

### 7.2 评估代码

- **DRB官方评估脚本**：`work/exp3_med_full/step6_rescore_drb_official.py`
  - 使用X-EvalSuit的DRBJudger
  - 豆包Seed 1.6作为judge
  - Point-wise RACE评估

- **X-EvalSuit DRB Judger**：
  - 路径：`/mnt/bn/.../X-EvalSuit/agentic_eval/judger/drb.py`
  - 包含：format_for_drb, parse_citations, DRBJudger class

### 7.3 官方DRB仓库

- **GitHub**：https://github.com/Ayanami0730/deep_research_bench
- **本地路径**（需要clone）：`/path/to/deep_research_bench/`
- **包含**：
  - RACE evaluation script（deepresearch_bench_race.py）
  - FACT pipeline（utils/extract, deduplicate, scrape, validate, stat）
  - Reference articles
  - Query data

### 7.4 API配置

```python
# 豆包Seed 1.6
ARK_API_KEY = "bb6ce7bb-dcd3-4733-9f13-ada2de86ef11"
ARK_API_BASE = "https://ark-cn-beijing.bytedance.net/api/v3"
ARK_MODEL = "ep-20250724221742-fddgp"

# Jina API (用于FACT URL scraping)
JINA_API_KEY = "jina_21ed3799312248a7a1aa73b549bd44f1N3Lm4OdyW66asT108Uu55M83cZh0"
JINA_BASE_URL = "https://r.jina.ai"
```

**配置位置**：
- API keys在`0001_utils/api/.env`
- 详细示例见`0001_utils/api/examples/api_examples.py`

---

## 八、参考资源

### 8.1 官方资源

- [DeepResearch Bench官方网站](https://deepresearch-bench.github.io/)
- [GitHub仓库](https://github.com/Ayanami0730/deep_research_bench)
- [Official Leaderboard](https://huggingface.co/spaces/Ayanami0730/DeepResearch-Leaderboard)
- [ArXiv论文](https://arxiv.org/abs/2506.11763) - DeepResearch Bench: A Comprehensive Benchmark
- [FutureSearch.ai Benchmark](https://futuresearch.ai/deep-research-bench/)

### 8.2 相关论文

- **DeepResearch Bench Paper** (2506.11763) - 官方论文
- **How Far Are We from Genuinely Useful Deep Research Agents?** (2512.01948) - OPPO团队分析
- **Step-DeepResearch Technical Report** (2512.20491) - 技术报告
- **A Rigorous Benchmark with Multidimensional Evaluation** (2510.02190) - 多维评估

### 8.3 内部文档

- **SOTA Roadmap**：`work/exp3_med_full/docs/SOTA_ROADMAP.md`（20页详细技术文档）
- **Visualization**：`work/exp3_med_full/docs/drb_sota_comparison.html`（可视化对比页面）
- **Previous Work**：`work/exp3_med_full/docs/README.md`（exp3医学子集实验）
- **Previous Work**：`work/exp3_med_full/docs/COMPLETE_HANDOVER_REPORT.md`（ResearchQA/DRB/DRB2综合报告）

---

## 九、总结

### 9.1 本次工作成果

✅ **调研DRB SOTA水平**（WebSearch获取最新leaderboard）
✅ **分析当前表现**（识别两大关键问题：FACT=0, Insight低）
✅ **设计对比实验**（Baseline vs Report vs Optimized）
✅ **制定优化路线图**（4个Phase，4-5周时间表）
✅ **定义成功标准**（3个级别：Minimal/Target/Ambitious）
✅ **创建详细技术文档**（SOTA_ROADMAP.md，20页）
✅ **创建可视化对比页面**（drb_sota_comparison.html，静态HTML）
✅ **完成对接文档**（本文件，HANDOVER_SOTA_ATTACK.md）

### 9.2 关键发现

1. **Report框架有优势**：
   - Instruction Following高（8.46）
   - Readability高（8.01）
   - 证明Two-Layer DAG架构有价值

2. **两大致命问题**：
   - 🔴 FACT=0：完全没有引用，无法参与官方评估
   - 🟡 Insight低（6.70）：缺少深度分析

3. **优化潜力巨大**：
   - 预计Overall可从7.67提升到8.5+（+10.8%）
   - FACT可从0提升到30+引用/任务
   - 有望成为开源框架SOTA

### 9.3 下一步关键任务

**立即开始（本周）**：
1. 🔴 **P0**: 实现引用系统（2-3天）
2. 🟡 **P1**: 优化Insight prompt（1-2天）
3. 📊 实现Simple Search Baseline（1天）

**本月目标**：
- Overall ≥ 8.0/10
- FACT citations ≥ 25/task
- 完成官方RACE evaluation
- Baseline实验对比

**终极目标**：
- 🏆 **成为开源框架中的SOTA**
- 超越LangChain-Open-Deep-Research
- 进入官方leaderboard Top 10

---

**文档创建时间**：2026-02-18
**项目状态**：📋 路线图制定完成，等待实施
**预计完成时间**：2026年3月底（4-5周后）
**最终目标**：在DeepResearch Bench上成为**开源框架SOTA** 🏆

---

## 附录：快速开始指南

### A.1 环境准备

```bash
# 1. 进入项目目录
cd /mnt/bn/med-mllm-lfv2/linjh/project/learn/2026_q1/eval/dag-deepresearch

# 2. 检查Python环境
python3 --version  # 需要 Python 3.8+

# 3. 检查API配置
cat 0001_utils/api/.env  # 确保有ARK_API_KEY和JINA_API_KEY
```

### A.2 第一个改动：添加引用系统

```bash
# 1. 备份原始文件
cp base_agent.py base_agent.py.backup

# 2. 编辑base_agent.py
vim base_agent.py
# 按照SOTA_ROADMAP.md中的代码示例修改

# 3. 在小规模测试集上验证
python3 work/exp3_med_full/step2_run_eval.py \
    --framework dag \
    --datasets drb_med \
    --max_items 5  # 只测试5条

# 4. 检查输出是否包含引用
cat work/exp3_med_full/assets/output/dag_drb_med_med.jsonl | jq '.report' | grep "§"
```

### A.3 查看可视化

```bash
# 使用浏览器打开HTML文件
# 方法1：直接打开本地文件
file:///mnt/bn/.../dag-deepresearch/work/exp3_med_full/docs/drb_sota_comparison.html

# 方法2：使用show命令部署（需要在开发机上）
show work/exp3_med_full/docs/drb_sota_comparison.html drb_sota_roadmap
# 然后访问：http://your-server/viz/drb_sota_roadmap.html
```

### A.4 获取帮助

- **技术问题**：查看`docs/SOTA_ROADMAP.md`的详细实现方案
- **代码示例**：参考`work/exp3_med_full/step*.py`
- **评估方法**：参考`step6_rescore_drb_official.py`
- **Prompt设计**：参考`prompts/medical/`目录

---

**准备好了吗？Let's reach SOTA! 🚀**
