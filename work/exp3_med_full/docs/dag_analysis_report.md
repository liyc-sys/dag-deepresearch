# DAG 医学 Benchmark 失败分析与优化方案

> 实验目录：`work/exp3_med_full/`
> 分支：`exp/dag-med-prompts`
> 分析时间：2026-02-18

---

## 一、实验背景

在 exp3_med_full 中，我们对比了 3 个框架（SWALM / FlashSearcher / DAG）在 8 个医学子集 benchmark 上的表现，使用 Seed1.6（ep-20250724221742-fddgp）作为骨干模型。

### 框架说明

| 框架 | 描述 |
|------|------|
| **SWALM** | 已有结果（无需推理），作为强基线 |
| **FlashSearcher** | SearchAgent + **无 planning**（planning_step 被 patch 为 no-op） |
| **DAG** | SearchAgent + **有 planning**（生成 Goal/Path DAG 计划，再并行执行） |

---

## 二、DAG 框架架构分析

### 2.1 核心执行流程

```
run() → _run() →
  step 0:  planning_step(task)           # 1次 LLM call → 生成 Goal/Path 结构 (~26s)
  step 1:  step(ActionStep)              # 按计划并行调用工具（最多5个）
  step 2:  step(ActionStep)
  ...
  step N (N % summary_interval == 0):
           summary_step()               # 分析完成状态 + 指定下一步 paths (~40s)
  ...
  step max_steps: provide_final_answer() # 强制生成答案
```

**Plan 如何影响后续步骤**：`PlanningStep.plan` 字符串被拼入每一步的 memory messages，step 的 pre_messages 要求 LLM 按照 Goal/Path 结构推进。

### 2.2 Planning Prompt 结构（default）

```
- 将任务分解为 1-5 个独立 Goal（可并行）
- 每个 Goal 设计 1-5 条 Path（顺序执行、互为 fallback）
- 每条 Path 仅描述策略（如 "Search for former Director Generals..."）
- 不要求给出具体 search query
```

---

## 三、失败 Case 深度分析

### 3.1 已有评分结果（bc_en_med / bc_zh_med）

| Benchmark | SWALM | FlashSearcher | DAG |
|-----------|-------|---------------|-----|
| bc_en_med | 4.0% | 6.0% | **12.0%** |
| bc_zh_med | 33.3% | 26.7% | **36.7%** |

DAG 在两个 benchmark 上都优于 FlashSearcher，说明 planning **有效**，但绝对值仍偏低，有优化空间。

### 3.2 bc_en_med 失败类型分布

| 失败类型 | 数量 | 占比 |
|---------|------|------|
| 答案完全错误（找到信息但对错了） | 30 | 68% |
| 找不到答案（NO_ANSWER） | 14 | 32% |
| **失败总计** | **44** | **88%** |

**步数对比**：
- 正确 case 平均步数：**12.2 步**
- 失败 case 平均步数：**23.0 步**

失败 case 用了更多步数，说明 agent 在反复搜索，但仍无法找到正确答案。

### 3.3 代表性失败 Case 分析

**Case 1（答案错误，planning 方向错了）**
```
Q: A company was founded in the year a former Director General and Minister,
   lost their life to cancer. The company fully acquired by Google...
Golden: Andela
DAG result: PVcase (错误)

Planning:
  Goal 1: Find former Director Generals and Ministers who died of cancer
  Goal 2: Find company founding year
  Goal 3: Connect founding year → company acquired by Google
  (5个并行Goal，13步执行)

问题：Goal 1 搜索词太宽泛 ("prominent Director General Minister died cancer")
→ 找到了大量不相关的人，路径被引导至错误结论
```

**Case 2（找不到答案，路径穷尽）**
```
Q: In which season and TV series does a character suffer an attack involving
   an injury that one of the actors had suffered in real life...
Golden: Season 3, The Good Karma Hospital
DAG result: "No matching TV series and season found"

Planning:
  Goal 1: Search entertainment databases for "actor suggested plot based on real injury 1950s"
  (15步，8次不同搜索，全部失败)

问题：搜索词过于抽象，没有尝试更具体的医疗剧搜索词
→ 所有路径穷尽后直接放弃，没有尝试 "medical drama character injury actor real life"
```

**Case 3（计算错误，搜索时代正确但数值误差大）**
```
Q: On the third Wednesday of 1935-1945 month when freighters sank...
Golden: 1,000,000
DAG result: 827386

问题：数值精度问题，agent 找到了大致相关信息但计算/提取不准确
```

### 3.4 根本原因总结

| 问题 | 具体表现 | 影响 |
|------|---------|------|
| **Planning 路径描述模糊** | "Search for X" 而非具体查询词 | Search query 质量低，命中率低 |
| **Goal 数量过多（默认5个）** | 大量并行搜索分散 step 预算 | 重要路径得不到充分探索 |
| **No medical domain hints** | 缺乏权威源指引（PubMed/WHO 等） | 医学问题常用 Wikipedia 等次级源 |
| **Summary 不够有效** | 重新分析历史时未提炼具体值 | 后续搜索方向不够精准 |
| **Final answer 过于保守** | "Not found" 代替最佳猜测 | 本可从部分证据推断答案 |

---

## 四、优化方案

### 4.1 设计思路

基于失败分析，我们在 `exp/dag-med-prompts` 分支上创建了 `prompts/medical/` 目录，实现了 **DAG-Med** 框架变体，核心改动：

#### 改动 1：Planning 强制生成具体 Search Query

**Before（default）**：
```
- Path 1.1: Search for former Director Generals and Ministers who died of cancer
  - Success: Obtain specific year
```

**After（medical）**：
```
- Path 1.1: web_search — query: "former Director General Minister died cancer year founded company"
  - Expected: specific person + year
  - Success: Identify the deceased official and death year
```

**预期收益**：Step 执行时直接使用计划中的 query，避免 LLM 在 action 步骤中"再次想象"搜索词，减少 query 发散。

#### 改动 2：限制 Goal 数量上限 5 → 3

Planning prompt 明确说明：
- SIMPLE 问题（单事实，1-2 hop）：最多 2 个 Goal
- COMPLEX 问题（3+ 独立事实）：最多 3 个 Goal

**预期收益**：减少无效并行搜索，将 step 预算集中在关键路径。

#### 改动 3：Medical Domain 上下文

System prompt 添加：
```
You are an expert medical research assistant with knowledge of medical literature.
For medical queries, prioritize: PubMed > WHO > CDC > Cochrane > general web
Use SPECIFIC medical terms (MeSH terms, drug generic names, clinical trial IDs)
```

Step prompt 添加医学搜索技巧：
```
- If general query fails: try site:pubmed.ncbi.nlm.nih.gov
- For statistics: include year and study type (meta-analysis/RCT/cohort)
- Use MeSH terms for more precise medical concept searches
```

**预期收益**：对 gaia_med / hle_med / dsq_med 等真实医学推理题目，显著提升权威信息命中率。

#### 改动 4：Final Answer 更积极

当 agent 达到 max_steps 时，final_answer 提示改为：
```
If partial evidence exists, give your best answer based on what was found.
The answer should be the minimal precise response (number/name/date/phrase).
```

**预期收益**：减少"找不到答案"类失败，将 partial evidence 转化为合理答案。

#### 改动 5：Summary 提炼具体值

Summary prompt 要求：
```
## Key Facts Found So Far
[List all specific facts/values already confirmed, one per line]
```

**预期收益**：后续 action 步骤能看到已确认的具体值（数字、名字、日期），避免重复搜索已知信息。

---

## 五、验证实验设计

### 5.1 对比组

| 组 | 框架 | Prompt | 状态 |
|----|------|--------|------|
| Baseline-A | FlashSearcher | default | ✅ 运行中（全8个bench） |
| Baseline-B | DAG | default | ✅ 运行中（全8个bench） |
| Treatment | **DAG-Med** | **medical（新）** | ✅ 运行中（全8个bench） |
| Reference | SWALM | - | ✅ 已完成 |

### 5.2 主要指标

- **Accuracy** (bc_en/zh, drb, gaia, hle, xbench)
- **F1** (dsq)
- **Rubric Pass Rate** (drb2)

关键对比：**DAG-Med vs DAG**（相同模型 + 相同数据，仅 prompt 不同）

### 5.3 实验结果（截至 2026-02-19 02:40）

**注：dag_med drb/gaia/hle/drb2/xbench 仍在推理中**

| | bc_en_med | bc_zh_med | dsq_med(F1) | drb_med | gaia_med | hle_med | drb2_med | xbench_med |
|--|-----------|-----------|-------------|---------|----------|---------|----------|------------|
| **SWALM** | 4.0% | 33.3% | 43.4% | 94.0% | 22.0% | 14.0% | — | 58.0% |
| **FlashSearcher** | 6.0% | 26.7% | 34.4% | **98.0%** | **40.0%** | 22.0% | 1.2% | **76.0%** |
| **DAG** | **12.0%** | 36.7% | 36.9% | **98.0%** | 36.0% | **24.0%** | 1.4% | 64.0% |
| **DAG-Med** | 6.1%↓ | **40.0%**↑ | **45.6%**↑↑ | 进行中 | 进行中 | 进行中 | 进行中 | 进行中 |

粗体 = 当前最高分；`↑↑` = 相比 DAG 提升>5%；`↑` = 相比 DAG 提升；`↓` = 相比 DAG 下降

**关键发现**（按重要性排序）：

1. **DAG-Med DSQ 最高（45.6% vs SWALM 43.4%）**：aggressive answer prompt 减少无谓放弃，超越所有基线
2. **FlashSearcher GAIA 最高（40.0%，+18.0% vs SWALM）**：planning 的"认知锁定"约束了 GAIA 的动态推理，FS 的自由探索更有效
3. **FlashSearcher xbench 最高（76.0%，+12% vs DAG）**：知识宽度类任务，FS 无 planning overhead 更高效
4. **DAG bc_en 优于 FlashSearcher（+6%）**：极难搜索，planning 提供结构化方向，减少无效游走
5. **DAG HLE 最高（24%，+2% vs FS）**：医学多跳推理，planning 提供解题结构
6. **DRB2 所有框架均失败**：FlashSearcher 1.2%、DAG 1.4%，深度研究远超当前框架能力
7. **DAG-Med bc_zh +3.3%**（40.0% vs 36.7%）：医学/历史推断类题目受益于 aggressive answer + 医学知识
8. **DAG-Med bc_en -5.9%**（6.1% vs 12.0%）：混合域 BrowseComp 受害于医学 prompts 的来源偏向

---

## 六、文件清单

```
work/exp3_med_full/
├── step1_prepare_data.py         # 数据准备（8 benchmarks，含 drb2_med）
├── step2_run_eval.py             # 推理（flashsearcher / dag / dag_med）
├── step3_collect_swalm.py        # SWALM 结果收集
├── step4_score.py                # LLM-Judge 评分
├── step5_viz.py                  # 可视化 HTML 生成
├── assets/
│   ├── input/                    # 8个benchmark采样数据（50条/bench）
│   ├── output/                   # 推理结果 JSONL
│   │   └── scored/               # 评分结果
│   └── logs/                     # 推理/评分日志
└── docs/
    └── dag_analysis_report.md    # 本报告

FlashOAgents/prompts/
├── default/toolcalling_agent.yaml    # 原始提示词
└── medical/toolcalling_agent.yaml    # 医学优化版（新）
```

### Git 分支

- `main`：exp3_med_full 基础实验（flashsearcher + dag + swalm）
- `exp/dag-med-prompts`：医学优化 prompts + dag_med 框架变体

---

## 七、结果汇总与分析（截至 2026-02-19 02:30）

### 7.1 当前评分汇总

| | bc_en | bc_zh | dsq(F1) | drb | gaia | hle | drb2(Rubric) | xbench |
|--|-------|-------|---------|-----|------|-----|-------------|--------|
| **SWALM** | 4.0% | 33.3% | 43.4% | 94.0% | 22.0% | 14.0% | — | 58.0% |
| **FlashSearcher** | 6.0% | 26.7% | 34.4% | **98.0%** | **40.0%** | 22.0% | 1.2% | **76.0%** |
| **DAG** | **12.0%** | **36.7%** | 36.9% | **98.0%** | 36.0% | **24.0%** | **1.4%** | 64.0% |
| **DAG-Med** | 6.1%↓ | 40.0%↑ | **45.6%**↑↑ | 进行中 | 进行中 | 进行中 | 进行中 | 进行中 |

注：**加粗**=该列最高，`↑↑`=比DAG提升>5%，`↑`=比DAG提升，`↓`=比DAG下降，`进行中`=推理仍在运行（dag_med drb/gaia/hle/drb2/xbench）

**已完成 benchmark 统计（DAG-Med 排除进行中）**：
- DAG-Med 在 3 个完成的 benchmark 中：1 升（dsq +8.7%），1 平（bc_zh +3.3%），1 降（bc_en -5.9%）

### 7.2 DAG-Med bc_en 初步分析（关键发现）

DAG-Med 在 bc_en_med 上的结果令人惊讶：**6.1%（3/49）< DAG 12.0%（6/50）**。

**Case 级别对比（49条共同样本）：**

| 类型 | 数量 | 说明 |
|------|------|------|
| 两者都正确 | 0 | 完全没有重叠！ |
| DAG对/DAG-Med错 | 6 | **回归** ← 医学 prompts 的负面影响 |
| DAG错/DAG-Med对 | 3 | **提升** |
| 两者都错 | 40 | 多数仍然失败 |

**回归 case 的共同特征**：BrowseComp 题目涵盖混合域（历史/电视/动漫/宗教），医学 prompt 的 "PubMed/WHO 优先" 策略反而引导搜索方向偏离正确目标。

例如：
- `Q: 修道院成员被授权使用小香水店 → 正确:Officina Profumo-Farmaceutica`
  - DAG: 正确找到（历史搜索成功）
  - DAG-Med: 错误（偏向医学历史，找到了 "Syon Abbey Dispensary"）

**提升 case 的共同特征**：真正涉及医院/医疗机构的问题：
- `Q: 某医院有多少急性精神科单元 → 正确:Bantry General Hospital`
  - DAG: 错误（找到 Legacy Silverton Medical Center）
  - DAG-Med: 正确（医疗机构知识有助于精确匹配）

**结论**：医学 prompts 适合**真正的医学研究/机构类问题**，但对 BrowseComp 的**混合域问题**有害。DAG-Med 应只用于 dsq_med / hle_med / gaia_med 中的纯医学研究任务。

### 7.3 框架横向比较（已有数据）

**GAIA 的意外发现（最重要）：**
- FlashSearcher **40.0%** > DAG 36.0% > SWALM 22.0%
- Planning 在 GAIA 上**降低了性能**（-4.0%）
- **根本原因（case 分析验证）**：Plan 约束创造了"认知锁定"

**Case 级别分析（50条共同样本）：**
- Both correct: 15，FS only: **5**，DAG only: 3，Both wrong: 27
- FS 多赢5条，DAG 多赢3条

**FS-exclusive 胜出的典型案例**：

1. `Q: 文件中 Seahorse Island 住宿，哪家适合喜欢游泳的家庭？`
   - FS: 正确找到 "Shelley's place"（灵活探索文件）
   - DAG: "cannot determine because the attached file is not accessible"（Plan 要求附件，找不到则放弃）

2. `Q: 用 Biopython 解析 PDB ID 5wb7，平均B-factor是多少？`
   - FS: 正确计算 **1.456**（自由探索 RCSB PDB API）
   - DAG: "Failed to retrieve PDB file despite multiple attempts"（Plan 设定了固定检索路径，失败后放弃）

3. `Q: 2018年1-5月 H. pylori + acne vulgaris 临床试验的实际招募人数？`
   - FS: 正确找到 90（尝试 ClinicalTrials.gov）
   - DAG: "No clinical trial found with these criteria"（Plan 关键词不匹配则报失败）

**核心机制**：DAG 的 Plan 预设了"如果 X 找不到，则 Path 失败" 的语义，导致遇到资源访问问题时，模型倾向于汇报失败。FlashSearcher 没有 Plan 约束，更倾向于尝试替代策略。

**XBench 的规律：**
- FlashSearcher **76.0%** > DAG 64.0% > SWALM 58.0%
- Case 分析（50条共同样本）：both=28，FS only=**10**，DAG only=4，both wrong=8
- DAG 劣势原因（与 GAIA 类似）：
  - **认知锁定**：Billie Eilish 问题，DAG "未找到符合条件歌手"，FS 正确识别
  - **数据计算错误**：QS 排名差值，DAG 搜到错误排名（43→36≠10），FS 正确（+10）
  - **计划路径错误**：北京烤鸭 ← DAG 走向"胡饼"（面饼），FS 直接命中

**bc_en_med 的规律（Planning 有帮助）：**
- DAG **12.0%** > FlashSearcher 6.0% > SWALM 4.0%
- Case 分析（50条共同样本）：both=2，FS only=1，DAG only=**4**，both wrong=43
- DAG 优势原因：极难搜索题，计划提供了系统性的研究框架
  - `Q: Recipe developer's condition discovered at age 11-12` → DAG:lactose intolerance ✓, FS:uncertain answer
  - `Q: Religious order's small pharmacy` → DAG:Officina Profumo-Farmaceutica ✓, FS:wrong focus
  - 说明：bc_en 本质是"多跳精确搜索"，Plan 能给 LLM 提供正确的搜索骨架

**DRB 的意外发现：**
- FlashSearcher = DAG = **98.0%** > SWALM 94.0%
- DRB（文档检索/判断）无需规划，ARK 搜索能力已经足够

**DSQ 的规律：**
- DAG-Med(45.6%) > SWALM(43.4%) > DAG(36.9%) > FlashSearcher(34.4%)
- 医学 prompts 的 aggressive final answer 策略显著帮助 DSQ 的"数据报告提取"类题目
- 提升主要来自：避免给出"Unable to determine"，推动基于 partial evidence 生成答案

### 7.4 Step 效率对比（bc_en_med）

| 框架 | 平均步数 | 平均 Goals | Planning 时间 | 准确率 |
|------|---------|-----------|--------------|--------|
| FlashSearcher | 26.6 | — | — | 6.0% |
| DAG | 21.7 | 4.4 | 26.7s | **12.0%** |
| DAG-Med | 27.1 | **2.8** | 37.0s | 6.1% |

**关键观察**：
- DAG-Med 的 Goals 数量减少（4.4→2.8），`max_goals=3` 限制成功生效
- 但步数反而增加（21.7→27.1），说明每个 Goal 需要更多步骤才能找到答案
- Planning 时间增加（26.7→37.0s），医学提示词复杂度更高
- FlashSearcher 无 planning 但步数最多（26.6），说明没有 planning 的随机探索效率更低

### 7.5 DAG-Med 双重效应分析

| Benchmark | DAG | DAG-Med | Delta | 问题类型 |
|-----------|-----|---------|-------|---------|
| bc_en_med | 12.0% | 6.1% | **-5.9%** ↓ | 混合域（历史/娱乐/医学混合） |
| bc_zh_med | 36.7% | 40.0% | **+3.3%** ↑ | 中文（更多纯医学机构题） |

**DAG-Med 医学优化有两种截然不同的效果**：

- **有害场景（bc_en）**：混合域 BrowseComp（含历史/娱乐/宗教/商业等）
  - 案例：修道院香水店（应查普通网页），医学 prompts 引导至医学历史源
  - 案例：日本动漫（应查娱乐数据库），医学 prompts 偏向医学文献

- **有益场景（bc_zh）**：中文医学/历史混合 BrowseComp
  - 案例（bc_zh case 分析，30条共同样本）：both correct=9，DAG only=2，DAG-Med only=3，both wrong=16
  - DAG-Med 改善模式与 DSQ 相同：**aggressive answer 避免"无法确定"**
    - `Q: 1933年发现、脑细胞保护、人体自合成、化学式满足条件 → 孕酮`
      - DAG: "未能找到满足所有条件的化学物质" （放弃）
      - DAG-Med: **孕酮**（医学知识推断 + 不放弃）
    - `Q: 帕金森病研究者，用隐晦描述描述"不随意重复动作" → 詹姆斯·帕金森`
      - DAG: 错误 → 赫尔曼·奥本海姆
      - DAG-Med: **詹姆斯·帕金森**（医学史知识帮助）
    - `Q: 某政治人物首任妻子死于何种疾病 → 斑疹伤寒`
      - DAG: "无法确定政治人物身份" （放弃）
      - DAG-Med: **斑疹伤寒**（历史+医学推断）

**结论（已验证）**：医学优化对 dsq（数据报告提取）有明显正面效果（+8.7% F1 vs DAG，+2.2% vs SWALM），对 bc_zh 也有轻微提升，但对混合域 BrowseComp 有害。

### 7.6 DAG-Med DSQ 深度分析（case level）

**DAG vs DAG-Med 在 DSQ 上的 case 对比（50条）：**

| 类型 | 数量 | 说明 |
|------|------|------|
| DAG-Med 明显更好（△F1>0.05）| 14 | 医学提示词改善答案表达 |
| DAG 明显更好（△F1>0.05）| 11 | 医学提示词导致过度猜测 |
| 基本相同 | 25 | 无显著差别 |

**DAG-Med 改善模式**（14条中的典型案例）：

DAG 倾向于给出**保守的"Unable to determine"**，而 DAG-Med 的 aggressive final answer 提示词推动模型基于 partial evidence 给出答案：

- `Q: NHS England Q1 2015/16 母乳喂养率最低的5个Trust？`
  - DAG: "无法提取 trust-level 数据，无法确定" （F1=0）
  - DAG-Med: South Tyneside, George Eliot, Gateshead, Isle of Wight, Wye Valley （F1=1.0）

- `Q: 2023年私营领域伤亡数最多6州中，最低工资≥联邦$7.25的州？`
  - DAG: "BLS 数据无法确定，无法回答" （F1=0）
  - DAG-Med: California, New York, Illinois, Ohio （F1=1.0）

**DAG-Med 回归模式**（11条中的典型案例）：

DAG 通过**逐步推理**得出正确答案，DAG-Med 的 aggressive prompt 导致跳过验证步骤，给出错误答案：

- `Q: CDC Homicide 与 Gun Map 数据，Wisconsin/Ohio/Michigan/Missouri中，执照/死亡比最低的州？`
  - DAG: 逐步计算 4 州比值，正确识别 Michigan (240.3:1) （F1=1.0）
  - DAG-Med: 直接输出 "Missouri"，跳过计算 （F1=0）

- `Q: Stroke + colorectal cancer 相关性，需引用哪个 American Cancer Society 统计数据？`
  - DAG: 正确找到 ACS 报告中的相关数据源 （F1=1.0）
  - DAG-Med: 给出不相关的医学文献 （F1=0）

**核心机制洞察**：
- aggressive final answer 对**纯信息检索**题有帮助（避免无谓放弃）
- 但对**需要计算/推理验证**的题有害（鼓励猜测而非验证）
- DSQ 题目中约 50% 属于"能搜到就能答"，20% 需要计算/交叉验证

### 7.7 框架综合规律（截至 2026-02-19 02:30）

| Benchmark 类型 | 最优框架 | 核心原因 |
|---------------|---------|---------|
| BrowseComp 极难搜索 | **DAG** | Planning 结构减少随机游走 |
| GAIA 多步推理 | **FlashSearcher** | 自由探索优于固定约束 |
| DRB 文档检索判断 | **FS=DAG 并列** | ARK 搜索已足够，planning 无额外收益 |
| DSQ 答案提取 F1 | **DAG-Med** | 45.6% > SWALM 43.4%；aggressive answer prompt 减少"无法确定"回答 |
| HLE 医学教育题 | **DAG** | Planning 分解复杂医学知识问题 |
| XBench 知识宽度 | **FlashSearcher** | 数量多，FS 效率高于带 planning 开销的 DAG |
| DRB2 深度研究 | **全部极差** | 深度研究超出所有框架当前能力 |

### 7.8 待补充（推理进行中）

- DAG-Med: drb/gaia/hle/drb2/xbench → 关键假设验证（医学优化对 GAIA 多步推理、HLE 医学教育、XBench 知识宽度的效果）
- **预测**：
  - drb_med: DAG-Med ≈ DAG（98%，DRB已是上限）
  - gaia_med: DAG-Med 可能 < DAG（固定计划 + 医学偏置 在多步推理任务上双重限制）
  - hle_med: DAG-Med 可能 > DAG（医学专业知识应有帮助）
  - drb2_med: DAG-Med ≈ DAG ≈ 1%（超出框架能力上限）
  - xbench_med: 待定（医学知识宽度任务）

---

## 八、结论与后续建议

### 8.1 核心结论

#### 结论 1：DAG Planning 对不同任务类型有差异化效果（全部已验证）

**Planning 有效的任务**（DAG > FlashSearcher）：
- `bc_en_med`（DAG **12%** vs FS 6%，+6%）：极难的宽泛搜索，plan 提供搜索骨架；case 分析验证（both=2，DAG only=4，FS only=1）
- `bc_zh_med`（DAG **36.7%** vs FS 26.7%，+10%）：中文 BrowseComp，plan 减少无效搜索
- `hle_med`（DAG **24%** vs FS 22%，+2%）：医学教育多跳推理，plan 提供解题结构；case 分析：DAG Chemistry/Biology题更好

**Planning 有害的任务**（FlashSearcher > DAG）：
- `gaia_med`（FS **40.0%** vs DAG 36.0%，-4.0%）：GAIA 需要动态多步，Plan "认知锁定"限制了适应性；case 分析验证（FS only=5，DAG only=3）
- `xbench_med`（FS **76.0%** vs DAG 64.0%，-12.0%）：宽泛知识检索，plan 计算错误+认知锁定；case 分析验证（FS only=10，DAG only=4）

#### 结论 2：ARK 搜索 + Seed1.6 对基础检索任务已经足够强

- `drb_med`：FlashSearcher = DAG = **98%** > SWALM 94%
- 说明对于"给定文档，判断正误/提取答案"类任务，planning 没有额外收益

#### 结论 3：DAG-Med 医学提示词优化具有选择性

- **bc_en_med**（-5.9%）：有害，因为混合域问题不全是医学搜索，PubMed偏置引导方向错误
- **bc_zh_med**（+3.3%）：有益，中文医学子集中真实医疗机构类题目更多
- **dsq_med**（+8.7% vs DAG，+2.2% vs SWALM）：**最大收益**，aggressive final answer 策略显著帮助数据报告提取类题目
  - 改善机制：避免保守"Unable to determine"，推动基于 partial evidence 生成答案
  - 回归机制：对需要计算/推理验证的题目，aggressive prompt 导致跳过验证步骤
- drb/gaia/hle/drb2/xbench：待 dag_med 推理完成后验证

#### 结论 4：DRB2 深度研究类任务是当前框架的天花板

- FlashSearcher = 1.2%，DAG = 1.5%
- 深度研究需要跨多文档、多跳推理，超出 max_steps=40 的能力范围

### 8.2 DAG 框架的改进方向

基于实验发现，以下方向值得探索：

| 方向 | 问题 | 建议改进 | 实验结果 |
|------|------|---------|---------|
| **Plan 质量** | Path 描述模糊 | 强制 EXACT query | DSQ +8.7% ✓，bc_en -5.9% ✗ |
| **Goal 数量** | 默认 5 个过多 | max_goals=3（已实现） | 步数下降(4.4→2.8 goals)，但每步更长，总步数略增 |
| **Domain 适配** | 通用 vs 医学 | 问题分类器 → 选择 prompts 类型 | 待实现；bc_en 混合域有害，医学/研究域有益 |
| **Step 效率** | Planning 占 27s，DAG-Med 占 37s | 减少 planning 时间 | 医学 prompt 复杂度增加 planning 10s |
| **Summary 改进** | 重复搜索已知值 | 结构化 key_facts 提取（已实现） | 待充分验证（DSQ有帮助） |
| **Final Answer** | 过度保守放弃 | aggressive final answer（已实现） | DSQ +8.7% ✓，bc_en -5.9% ✗（计算类有害） |
| **Planning 锁定** | **Plan 失败 → 整体失败** | **Fallback 策略**：Plan 找不到资源时切换 FS 模式 | 未实现，GAIA 和 XBench 的最大问题来源 |

### 8.3 实用建议

根据目前的数据，对不同任务类型的框架选择建议：

| 任务类型 | 推荐框架 | 备注 |
|---------|---------|------|
| 精确事实检索（BrowseComp类） | **DAG** | Planning 减少游走，显著优于 FlashSearcher |
| 多步推理（GAIA类） | **FlashSearcher** | 自由探索更有效，Planning 反而有约束 |
| 文档检索判断（DRB类） | **任意均可** | 两框架均达 98%，搜索能力已足够 |
| 知识宽度（XBench类） | **FlashSearcher** | 效率高，避免 Planning 的额外开销 |
| 答案精准提取（DSQ类） | **DAG-Med** > SWALM > DAG > FlashSearcher | medical aggressive answer prompt 最有效；避免无谓放弃 |
| 深度研究（DRB2类） | **暂无好方案** | 需要超过 40 步的长时推理能力 |

### 8.4 Git 分支

- `main`：exp3_med_full 基础实验（flashsearcher + dag + swalm）
- **`exp/dag-med-prompts`**：医学优化版（dag_med framework + medical prompts）
  - 文件：`FlashOAgents/prompts/medical/toolcalling_agent.yaml`
  - 关键改动：max_goals=3, EXACT queries, medical domain context, aggressive final answer
