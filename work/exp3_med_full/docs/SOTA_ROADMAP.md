# DRB SOTA攻关路线图

## 目标

将Report框架（Two-Layer DAG）在DeepResearch Bench上达到SOTA水平

---

## 当前状况

### Report框架 - 当前表现（2026-02-18）

**使用模型**：Seed 1.6 (ep-20250724221742-fddgp)
**评估方法**：Point-wise RACE（简化版，无reference对比）
**数据集**：DRB医学子集（50条任务）

| 维度 | 分数 | 说明 |
|------|------|------|
| **Comprehensiveness** | 7.40/10 | 信息覆盖的广度和深度 |
| **Insight** | **6.70/10** ⚠️ | 分析深度和洞察力（最弱项） |
| **Instruction Following** | 8.46/10 | 任务指令遵循程度 |
| **Readability** | 8.01/10 | 可读性和结构清晰度 |
| **Overall** | **7.67/10** | 整体质量 |

**FACT统计**（引用准确性）：
- 包含引用的样本：**0/50 (0.0%)** ❌ **致命问题！**
- 平均引用数：0.00
- 平均唯一URL数：0.00

**换算百分比**：7.67/10 = **76.7%**

---

## DRB Leaderboard SOTA（2026年2月）

来源：[DeepResearch Bench Official Leaderboard](https://huggingface.co/spaces/Ayanami0730/DeepResearch-Leaderboard)

| 排名 | 系统 | RACE Score | 说明 |
|------|------|-----------|------|
| 🥇 1 | Qianfan-DeepResearch Pro | - | 2026-02-03 登顶 |
| 🥈 2 | Qianfan-DeepResearch | - | 官方系统 |
| 🥉 3 | Gemini-2.5-Pro Deep Research | **48.88** | 之前的SOTA |
| 4 | OpenAI Deep Research | **46.98** | OpenAI官方 |
| - | MiroFlow-English | 72.19 (checklist) | 不同评分体系 |
| 6 | LangChain-Open-Deep-Research | - | **首个开源框架**（GPT-4.1 + Tavily）|

**注意**：
1. 官方RACE使用归一化评分（target/(target+reference)），与我们的point-wise评分不完全可比
2. Leaderboard上的分数可能使用加权计算或其他复杂公式
3. 需要用官方evaluation script才能得到可比的分数

---

## 对比实验设计

### 框架对比表格（目标）

| 模型 | 框架 | Comprehensiveness | Insight | Instruction Following | Readability | Overall | FACT Citations |
|------|------|-------------------|---------|---------------------|-----------|---------|----------------|
| Seed 1.6 | **无规划Baseline** | ? | ? | ? | ? | ? | ? |
| Seed 1.6 | **Report (当前)** | 7.40 | 6.70 | 8.46 | 8.01 | **7.67** | **0.00** ❌ |
| Seed 1.6 | **Report (优化后)** | **目标: 8.5+** | **目标: 8.0+** | **目标: 9.0+** | **目标: 8.5+** | **目标: 8.5+** | **目标: 50+** |

### 需要实现的Baseline

1. **无规划框架**（Simple Search Agent）
   - 只有搜索+生成，没有planning step
   - 类似FlashSearcher但不用DAG规划
   - 目的：证明Two-Layer DAG的价值

2. **单层规划框架**
   - 有outline但不做并行section research
   - 串行生成各section
   - 目的：证明并行化的价值

---

## 致命问题分析

### ❌ Critical Issue #1: FACT=0（无引用）

**问题**：当前Report框架生成的报告完全没有引用，FACT得分为0

**原因分析**：
1. Report生成时没有记录search结果的traces
2. 没有在report中添加引用标记（如[1], [2]）
3. 没有在report末尾添加References section

**影响**：
- FACT框架完全无法评估（引用准确性是DRB的核心指标）
- 在官方leaderboard上会严重失分
- 无法与其他系统公平对比

**优先级**：🔴 **P0 - 必须立即修复！**

---

### ⚠️ Major Issue #2: Insight偏低（6.70/10）

**问题**：Insight维度得分显著低于其他维度

**可能原因**：
1. Section research prompt不够强调"深度分析"和"洞察"
2. 只做信息收集，缺少批判性思考
3. 没有跨section的综合分析
4. 缺少forward-looking thinking

**对比其他维度**：
- Instruction Following: 8.46（说明任务理解没问题）
- Readability: 8.01（说明结构组织良好）
- Comprehensiveness: 7.40（说明信息覆盖尚可）

**优先级**：🟡 **P1 - 重要优化点**

---

## 优化路线图

### Phase 1: 修复致命问题（预计提升 +10-15分）

#### 1.1 添加完整引用系统 🔴 P0

**目标**：将FACT从0提升到50+引用/任务

**实现方案**：

1. **记录search traces**
   ```python
   # 在SearchAgent中添加
   self.search_traces = {}  # {snippet_id: {Title, URL, Snippet}}

   def search(self, query):
       results = self._call_search_api(query)
       for i, result in enumerate(results):
           snippet_id = f"§{len(self.search_traces) + 1}"
           self.search_traces[snippet_id] = {
               "Title": result["title"],
               "URL": result["url"],
               "Snippet": result["snippet"]
           }
       return results
   ```

2. **在report中添加引用标记**
   ```python
   # Section生成时
   prompt = f"""
   Write a section about {section_topic}.

   **IMPORTANT**: When stating facts, add citation marks like [§1], [§2].
   Use the search results you retrieved earlier.

   Search Results:
   {formatted_search_results}
   """
   ```

3. **添加References section**
   ```python
   def finalize_report(self, report_body, search_traces):
       # Parse citations from report
       citations = extract_citations(report_body)  # [§1, §2, ...]

       # Build references
       references = []
       for cid in citations:
           if cid in search_traces:
               url = search_traces[cid]["URL"]
               references.append(f"[{cid}] {url}")

       # Append to report
       if is_chinese(report_body):
           report += "\n\n## 参考文献\n" + "\n".join(references)
       else:
           report += "\n\n## References\n" + "\n".join(references)

       return report
   ```

**验证指标**：
- 平均引用数 ≥ 30
- 引用覆盖率 ≥ 80%（80%的关键facts有引用）
- Citation accuracy（需要FACT validation）≥ 70%

**时间估计**：2-3天

---

#### 1.2 改进Prompt - 强化Insight要求 🟡 P1

**目标**：将Insight从6.70提升到8.0+

**实现方案**：

1. **Section Research Prompt优化**
   ```python
   # 当前prompt（简化版）
   "Write a comprehensive section about {topic}. Include relevant facts and data."

   # 优化后prompt（强调分析和洞察）
   """
   Write an insightful and analytical section about {topic}.

   Requirements:
   1. **Deep Analysis**: Don't just list facts - analyze WHY and HOW
   2. **Critical Thinking**: Evaluate different perspectives and identify key issues
   3. **Causal Relationships**: Explain cause-effect relationships and underlying mechanisms
   4. **Implications**: Discuss implications and potential solutions
   5. **Forward-Looking**: Consider future trends and developments

   Structure:
   - Overview (context and background)
   - Key Findings (with analysis, not just facts)
   - Critical Analysis (evaluate and synthesize)
   - Implications and Insights

   Cite all facts with [§N] references.
   """
   ```

2. **添加"Synthesis & Insights" Section**
   - 在outline generation时，自动添加一个综合分析section
   - 跨越各section进行综合分析
   - 提供高层次的洞察和建议

3. **Multi-round Refinement**（可选，cost较高）
   - 生成初稿后，用LLM review并指出"缺少深度分析"的地方
   - 重新生成相应section

**验证指标**：
- Insight score ≥ 8.0/10
- 报告中"分析性"语句比例 ≥ 30%（vs 纯事实陈述）

**时间估计**：1-2天

---

### Phase 2: 系统优化（预计提升 +5-10分）

#### 2.1 优化Outline Planning 🟢 P2

**目标**：提升Comprehensiveness到8.5+

**优化方向**：
1. **更细粒度的section划分**
   - 从5-6个sections → 8-10个sections
   - 每个section更聚焦，减少信息遗漏

2. **动态调整outline**
   - 第一轮搜索后，根据发现的新信息调整outline
   - 添加missing topics

3. **Topic coverage validation**
   - 用LLM检查outline是否覆盖了问题的所有方面
   - 补充遗漏的关键维度

**时间估计**：2-3天

---

#### 2.2 优化Search质量 🟢 P2

**目标**：提升search结果的相关性和覆盖度

**优化方向**：
1. **Query diversification**
   - 为每个section生成3-5个不同角度的query
   - 覆盖不同时间、地域、视角

2. **去重和ranking**
   - 对search结果去重（URL-level + semantic-level）
   - 根据相关性和权威性排序

3. **Iterative search**（可选）
   - 如果首轮search结果不足，自动生成follow-up queries

**时间估计**：2-3天

---

#### 2.3 提升Readability（保持8+） 🟢 P3

**目标**：保持或提升可读性

**优化方向**：
1. **结构优化**
   - 添加Executive Summary
   - 每个section添加小标题
   - 使用bullet points和表格

2. **语言优化**
   - 避免过于技术化的术语堆砌
   - 添加过渡句，增强连贯性

**时间估计**：1-2天

---

### Phase 3: 官方评估对齐（获得可比分数）

#### 3.1 使用官方RACE evaluation 🔵 P1

**问题**：当前使用的是point-wise RACE（简化版），与官方leaderboard不可比

**解决方案**：

1. **获取reference articles**
   - DRB官方提供了reference articles
   - 路径：`/path/to/drb/data/reference_articles/`

2. **使用官方evaluation script**
   ```bash
   # 在DRB repo中运行
   python deepresearch_bench_race.py \
       report_drb_med \
       --raw_data_dir data/test_data/raw_data \
       --max_workers 10 \
       --query_file data/prompt_data/query.jsonl \
       --output_dir results/race/report_drb_med
   ```

3. **修改judge为豆包**（降低成本）
   - 当前官方用Gemini-2.5-Pro（贵）
   - 改用豆包Seed 1.6（便宜）
   - 验证与Gemini的相关性

**验证指标**：
- 获得归一化RACE分数（0-1 scale）
- 可以在leaderboard上对比

**时间估计**：2-3天

---

#### 3.2 完整FACT evaluation 🔵 P2

**目标**：获得citation accuracy和effective citations指标

**流程**：
1. Extract citations from reports
2. Deduplicate URLs
3. Scrape URLs with Jina API
4. Validate citations against scraped content
5. Calculate metrics

**使用官方pipeline**：
```bash
# Extract
python -m utils.extract --raw_data_path data.jsonl --output_path extracted.jsonl

# Deduplicate
python -m utils.deduplicate --raw_data_path extracted.jsonl --output_path dedup.jsonl

# Scrape
python -m utils.scrape --raw_data_path dedup.jsonl --output_path scraped.jsonl

# Validate
python -m utils.validate --raw_data_path scraped.jsonl --output_path validated.jsonl

# Stat
python -m utils.stat --input_path validated.jsonl --output_path result.txt
```

**验证指标**：
- Citation accuracy ≥ 80%
- Effective citations ≥ 30 per task

**时间估计**：2-3天（主要是API调用和scraping）

---

### Phase 4: 扩展到完整DRB（50 EN + 50 CN）

#### 4.1 扩展到完整100任务

**当前状态**：只在50条医学子集上测试

**扩展计划**：
1. 在完整DRB上运行（100条任务，22个领域）
2. 分析不同领域的表现差异
3. 针对性优化weak domains

**时间估计**：1周（主要是推理时间）

---

#### 4.2 提交官方Leaderboard

**目标**：在官方leaderboard上获得排名

**流程**：
1. 按照官方格式准备submission
2. 运行完整RACE+FACT evaluation
3. 提交到Hugging Face Space

**时间估计**：1-2天

---

## 模型升级路线（可选）

当前使用：**Seed 1.6**

可选升级：
1. **GPT-4.1** - 更强推理能力，可能提升Insight
2. **Claude Opus 4.6** - SOTA模型，更好的分析和综合能力
3. **Gemini-2.5-Pro** - DRB官方judge使用的模型

**注意**：先在Seed 1.6上优化框架，再考虑换模型，否则无法分离框架vs模型的贡献

---

## Baseline实验计划

### Exp A: 无规划Baseline

**实现**：
- 移除planning step
- 直接对question进行search
- 一次性生成完整report
- 对比证明planning的价值

**预期结果**：
- Comprehensiveness下降（缺少系统性规划）
- Insight下降（缺少结构化分析）
- Overall下降2-3分

---

### Exp B: 单层规划（串行）

**实现**：
- 保留outline planning
- 但串行生成各section（不并行）
- 对比证明并行化的价值

**预期结果**：
- 质量类似，但时间显著增加（3-5x）

---

### Exp C: Report框架（优化后）

**实现**：
- Phase 1所有优化
- 完整引用系统
- 优化后的prompts

**预期结果**：
- Overall ≥ 8.5/10
- FACT citations ≥ 30
- 显著优于Baseline A和B

---

## 时间线（估算）

| 阶段 | 任务 | 时间 | 优先级 |
|------|------|------|--------|
| **Week 1** | 添加引用系统（P0） | 2-3天 | 🔴 Critical |
| **Week 1** | 优化Insight prompt（P1） | 1-2天 | 🟡 High |
| **Week 2** | 优化Outline Planning（P2） | 2-3天 | 🟢 Medium |
| **Week 2** | 优化Search质量（P2） | 2-3天 | 🟢 Medium |
| **Week 3** | 官方RACE evaluation（P1） | 2-3天 | 🔵 High |
| **Week 3** | 完整FACT evaluation（P2） | 2-3天 | 🔵 Medium |
| **Week 4** | Baseline实验（A、B） | 3-4天 | 🟢 Medium |
| **Week 4** | 完整100任务评估 | 2-3天 | 🟢 Medium |
| **Week 5** | 结果分析和论文撰写 | 5-7天 | 📝 Writing |

**总计**：约4-5周达到SOTA水平

---

## 成功指标

### Minimal Success（最低成功标准）

- [ ] FACT citations ≥ 20 per task（从0提升）
- [ ] Insight ≥ 8.0/10（从6.70提升）
- [ ] Overall ≥ 8.0/10（从7.67提升）
- [ ] 显著优于无规划baseline

### Target Success（目标标准）

- [ ] FACT citations ≥ 30 per task
- [ ] Citation accuracy ≥ 80%
- [ ] Overall ≥ 8.5/10
- [ ] 进入官方leaderboard Top 10

### Ambitious Success（理想标准）

- [ ] Overall ≥ 9.0/10
- [ ] 官方leaderboard Top 5
- [ ] 成为**开源框架中的SOTA**（超越LangChain-Open-Deep-Research）

---

## 风险和挑战

### 风险1：引用系统实现复杂

**挑战**：需要大幅修改现有代码，可能引入bugs

**缓解措施**：
- 先在小规模测试集（5条）上验证
- 保持向后兼容，不破坏现有功能
- 增加单元测试

---

### 风险2：Insight提升困难

**挑战**：深度分析依赖模型能力，prompt优化效果有限

**缓解措施**：
- 尝试多个prompt变体，A/B测试
- 考虑添加multi-round refinement
- 如果Seed 1.6不够，升级到GPT-4.1

---

### 风险3：官方评估不一致

**挑战**：官方RACE使用Gemini-2.5-Pro，我们用豆包可能不一致

**缓解措施**：
- 同时运行Gemini和豆包，计算相关性
- 如果相关性低，考虑使用Gemini（虽然贵）
- 在论文中report两种judge的结果

---

## 下一步行动

### 立即开始（本周）

1. **🔴 P0**: 实现引用系统
   - [ ] 修改SearchAgent记录traces
   - [ ] 修改prompt要求添加引用
   - [ ] 添加References section生成
   - [ ] 在5条任务上测试

2. **🟡 P1**: 优化Insight prompt
   - [ ] 重写section research prompt
   - [ ] 添加Synthesis section
   - [ ] 在5条任务上A/B测试

3. **📊 Baseline**: 实现无规划baseline
   - [ ] 创建simple search agent（no planning）
   - [ ] 在50条任务上运行
   - [ ] 对比Report框架

### 本月完成

- Phase 1全部任务（引用+Insight）
- Phase 3.1（官方RACE evaluation）
- Baseline实验A

### 下月目标

- Phase 2全部任务（系统优化）
- Phase 3.2（完整FACT evaluation）
- 完整100任务评估
- 提交官方leaderboard

---

## 参考资源

### 官方资源

- [DeepResearch Bench 官方网站](https://deepresearch-bench.github.io/)
- [DeepResearch Bench GitHub](https://github.com/Ayanami0730/deep_research_bench)
- [Official Leaderboard](https://huggingface.co/spaces/Ayanami0730/DeepResearch-Leaderboard)
- [ArXiv论文](https://arxiv.org/abs/2506.11763)

### 代码资源

- X-EvalSuit DRB Judger: `/mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/X-EvalSuit/agentic_eval/judger/drb.py`
- 当前Report框架: `dag-deepresearch/base_agent.py`
- FlashOAgents: `dag-deepresearch/FlashOAgents/`

---

**创建时间**：2026-02-18
**作者**：Claude Sonnet 4.5
**状态**：🚀 Ready to Start
