# exp4_report_drb: DRB评估对齐 + Report框架全面优化

## 实验目标

将exp3的DRB评估从自定义5维度评分对齐到官方RACE评估（reference-based 4维度），并通过prompt和架构优化提升Report质量。

**核心问题**: exp3在DRB评估上使用了自定义5维度评分（1-5分制），与官方DRB评估（RACE 4维度 reference-based）完全不同，导致结果无法与leaderboard对比。

**解决方案**:
1. 彻底对齐官方RACE评估：`score = target/(target+ref)`，>0.5表示优于reference
2. 全面优化Report框架：从Prompt、架构参数、搜索深度等多维度优化

## 目录结构

```
exp4_report_drb/
├── docs/
│   ├── task1.md                      # 原始任务计划
│   └── README.md                     # 本文档
├── assets/
│   ├── input/                        # 符号链接到exp3数据
│   │   ├── drb_med_med.jsonl         # DRB问题集(50条)
│   │   ├── exp3_report_drb_med_med.jsonl  # exp3的Report结果
│   │   ├── reference.jsonl           # 官方reference articles(100条,其中50条匹配)
│   │   └── criteria.jsonl            # 官方评估标准(100条,其中50条匹配)
│   ├── output/
│   │   ├── report_v2_drb_med.jsonl   # v2优化后的Report结果(🔄 10/50完成)
│   │   ├── comparison_report.html    # (step4产出) 对比可视化
│   │   └── scored/
│   │       ├── baseline_race_scored.jsonl      # ✅ baseline RACE评分(50条)
│   │       ├── baseline_race_scored_summary.json
│   │       ├── v2_race_scored.jsonl            # ⏳ v2 RACE评分(待step2全量完成)
│   │       ├── v2_test_race_scored.jsonl       # ✅ v2 RACE评分(2条测试)
│   │       └── v2_test_race_scored_summary.json
│   └── logs/
│       ├── step1_baseline_race.log
│       ├── step2_test.log
│       ├── step2_full_run.log        # 🔄 全量推理日志(持续写入)
│       └── step3_v2_test.log
├── prompts/
│   └── report_prompts_v2.yaml        # 优化后的Report prompt配置
├── step1_baseline_race.py            # baseline RACE评估
├── step2_optimize_prompts.py         # 优化推理脚本
├── step3_race_eval.py                # 通用RACE评估脚本
└── step4_compare.py                  # 对比分析+可视化
```

## 执行状况

### Step 1: Baseline RACE评估 ✅ 完成

用exp3的Report结果（50条）跑官方RACE评估:
- Judge模型: 豆包 Seed 1.6 (`ep-20250724221742-fddgp`)
- 评分方式: reference-based comparative scoring
- 归一化: `score = target / (target + reference)`, >0.5表示优于reference

**Baseline结果:**
| 维度 | 全量(50) | 中文(25) | 英文(25) |
|------|----------|----------|----------|
| Comprehensiveness | 0.4276 | 0.4331 | 0.4222 |
| Insight | 0.3989 | 0.3964 | 0.4014 |
| Instruction Following | 0.4681 | 0.4691 | 0.4671 |
| Readability | 0.4557 | 0.4590 | 0.4523 |
| **Overall Score** | **0.4316** | **0.4334** | **0.4298** |

结论: 全部低于0.5，说明exp3的Report整体弱于reference article。Insight是最薄弱维度(0.3989)。

### Step 2: 优化推理 🔄 进行中（10/50已完成）

**优化策略（三阶段）:**
1. **Planning阶段**: 要求提取所有显式/隐式需求，section数6-10，每个section有精确searchable query
2. **Research阶段**: 多角度搜索(≥3)，权威来源优先(PubMed/WHO)，每个claim必须有引用URL
3. **Synthesis阶段**: 学术级写作，平滑过渡，交叉引用，比较表格，3000-6000字

**架构参数优化:**
| 参数 | exp3默认 | v2优化 | 说明 |
|------|---------|--------|------|
| max_section_steps | 20 | 30 | 更深入搜索 |
| summary_interval | 6 | 8 | 更多搜索后再总结 |
| section_concurrency | 5 | 4 | 减少API限流 |
| max_section_retries | 2 | 3 | 更稳健 |
| prompts_type | default | medical | 医学优化prompts |

**V2报告质量对比:**
| 指标 | exp3 baseline | v2 optimized (10条) | 倍数 |
|------|--------------|--------------|------|
| 平均报告长度(字符) | 10,081 | 44,600 | 4.4x |
| section数量 | 4-6 | 10 | ~2x |
| 引用数量/篇 | ~10 | 60+ | ~6x |
| 平均生成时间(s) | ~300 | ~3,044 | ~10x |

**已完成10条详情:**
| task_id | 报告长度 | 耗时(s) | 问题摘要 |
|---------|---------|---------|---------|
| 24 | 33,779 | 3,613 | 如何增强自闭症学生课堂参与度 |
| 25 | 20,958 | 3,384 | 中性粒细胞在脑缺血急性期和慢性期的功能 |
| 26 | 58,821 | 3,365 | CD8+ T细胞线粒体动力学 |
| 27 | 30,204 | 3,037 | AI心理咨询和人类心理咨询有机结合 |
| 28 | 49,852 | 2,675 | 药物研究多组学角度解析 |
| 42 | 49,687 | 1,885 | 教育强国学生体质强健计划 |
| 48 | 22,849 | 3,377 | 五十三岁健康食谱营养搭配 |
| 49 | 48,810 | 3,259 | 20-30岁女性口腔正畸和医美需求 |
| 50 | 65,910 | 3,143 | 孩子身心健康成长学习生活安排 |
| 75 | 65,131 | 2,706 | Therapeutic interventions plasma modulation |

**2条v2 vs baseline RACE快速验证:**
| 维度 | v2(2条) | baseline(50条avg) | 提升 |
|------|---------|---------|------|
| Comprehensiveness | 0.4963 | 0.4276 | +0.0687 |
| Insight | 0.4687 | 0.3989 | +0.0698 |
| Instruction Following | 0.5036 | 0.4681 | +0.0355 |
| Readability | 0.4834 | 0.4557 | +0.0277 |
| **Overall Score** | **0.4864** | **0.4316** | **+0.0548** |

**全量运行状态:** 40条剩余，并发2，在后台持续运行（进程PID 36665）

### Step 3: v2 RACE评估 ⏳ 待step2完成

```bash
# step2全量完成后执行:
cd /mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/dag-deepresearch/work/exp4_report_drb
python3 step3_race_eval.py --input assets/output/report_v2_drb_med.jsonl --tag v2 2>&1 | tee assets/logs/step3_v2_full.log
```

### Step 4: 对比分析+可视化 ⏳ 待step3完成

```bash
# step3完成后执行:
python3 step4_compare.py
show assets/output/comparison_report.html exp4_drb_compare "exp4 DRB RACE: Baseline vs V2 comparison"
```

## 代码细节

### step1_baseline_race.py
- 通过`question`字段匹配exp3输出 ↔ reference/criteria的`prompt`字段
- 使用官方`generate_merged_score_prompt`构建评分prompt
- article_1=我们的report, article_2=reference article
- 并发5线程调用豆包Seed 1.6 judge
- 断点续跑支持（通过task_id检查已有结果）
- **关键**: `load_dotenv`必须在`import DRB`之前，否则JINA_API_KEY缺失会报错

### step2_optimize_prompts.py
- 加载自定义`prompts/report_prompts_v2.yaml`覆盖默认prompt（`orchestrator.prompts = custom_prompts`）
- 直接将question作为topic传入ReportOrchestrator（DRB不需要"Final Answer"包装）
- 每条创建独立的OpenAIServerModel和ReportOrchestrator实例（避免状态污染）
- 支持断点续跑（通过question字段去重）和并发控制（`--concurrency`参数）
- 输出格式与exp3完全兼容（question, report, task_id等字段）

### step3_race_eval.py
- 通用RACE评估：支持任意report JSONL文件
- 通过`--tag`参数区分不同实验的输出（如`--tag v2`生成`v2_race_scored.jsonl`）
- 与step1逻辑一致但更通用，支持`--model`, `--workers`, `--limit`参数
- 断点续跑：检查output文件中已有的task_id

### step4_compare.py
- 按task_id匹配baseline和v2结果
- 计算各维度delta和百分比变化
- 分语言(zh/en)统计
- 生成静态HTML可视化报告（summary cards + bar charts + language breakdown + per-item table + top improvers/decliners）

### prompts/report_prompts_v2.yaml
- **report_planning**: 增加"CRITICAL: Instruction Analysis"，要求提取ALL explicit/implicit requirements，每个requirement映射到至少一个section
- **section_research**: 增加"Research Standards"，7条标准（breadth, depth, recency, authority, citation, counterpoints, specificity）
- **report_synthesis**: 增加"Writing Standards"，8条标准（academic tone, smooth transitions, executive summary, analytical depth, data presentation, citation format, language matching, length）

## 与官方RACE评估的对齐分析

### 完全对齐的部分（直接import官方代码）
- 评分Prompt（`generate_merged_score_prompt` 中/英文）
- 加权分数计算（`calculate_weighted_scores`）
- JSON解析（`extract_json_from_markdown`）
- 归一化公式：`target / (target + reference)`
- article分配：article_1=target（我们的report），article_2=reference（官方参考文章）
- criteria/reference匹配逻辑（通过prompt字段匹配）

### 未对齐的差异
| 差异项 | 官方 | exp4 | 影响程度 |
|--------|------|------|---------|
| Judge模型 | Gemini 2.5 Pro + thinking_budget=16000 | 豆包Seed 1.6, temp=0.1, max_tokens=8192 | 高（绝对分数不可直接比较leaderboard） |
| Article Cleaning | 评分前用ArticleCleaner清洗 | 无，直接用原始report | 中 |
| 语言检测 | 从数据读取language标签 | 启发式检测（中文字符占比>20%） | 低 |

**结论**: 算法层面完全对齐，用同一个judge做baseline vs v2的相对对比完全合理。绝对分数因judge模型不同，不可直接与官方leaderboard比较。

## 依赖关系

| 依赖 | 路径 |
|------|------|
| FlashOAgents (Report框架) | `../../FlashOAgents/` |
| DRB官方仓库 | `../exp3_med_full/official_repos/deep_research_bench/` |
| API配置(.env) | `../../../../0001_utils/api/.env` |
| 豆包Seed 1.6 | endpoint: `ep-20250724221742-fddgp` |

## 后续计划

1. **等step2全量完成** → 检查进度: `wc -l assets/output/report_v2_drb_med.jsonl`
2. **跑step3 RACE评估** → 命令见上方Step 3
3. **跑step4对比分析** → 命令见上方Step 4，用show部署HTML
4. **根据结果迭代优化**:
   - 如果Insight仍低 → 加强synthesis prompt中的分析深度要求
   - 如果某些题目下降 → 分析原因，针对性调整
   - 如果引用率低 → 加强research阶段的URL保留要求
   - 如果Comprehensiveness不够 → 增加section数量上限
