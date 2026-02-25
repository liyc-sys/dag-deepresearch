# exp2_eval — DAG-DeepResearch 评测实验

## 实验目标

使用 [DAG-DeepResearch](../../) 框架（FlashSearcher + DAG 规划，基于 Seed1.8）对多个 Benchmark 进行推理评测，并与以下两个基线对比：

- **SWALM (Seed1.8)**：历史基线，使用 `CascadedFIFOCondenser` 压缩历史，稳定推理
- **FlashSearcher (GPT-4.1)**：GPT-4.1 直接驱动 FlashSearcher，无 DAG 规划

评测覆盖 **6 个 Benchmark**：3 个通用 + 3 个医疗领域子集。

---

## 代码结构

```
exp2_eval/
├── step1_prepare_data.py      # 准备通用 benchmark 数据（bc_en/bc_zh/dsq，各采样50条）
├── step1b_prepare_medical.py  # 准备医疗 benchmark 数据（来自 exp6_medical_subset，各30条）
├── step2_run_eval.py          # 批量推理脚本（多进程，支持断点续跑）
├── step3_score.py             # LLM-Judge 评分（BrowseComp用准确率，DSQ用F1）
├── step4_analyze_viz.py       # 生成静态 HTML 可视化报告
├── run_eval.sh                # 快捷运行脚本
├── assets/
│   ├── input/                 # 输入数据集（jsonl）
│   ├── output/                # 推理结果（jsonl）
│   │   └── scored/            # 评分结果（scored.jsonl + summary.json）
│   └── logs/                  # 运行日志
└── docs/
    ├── task1.md               # 原始任务文档
    ├── task1/analysis_report.md  # 案例分析报告
    └── README.md              # 本文件
```

---

## 模型配置

| 标识 | 模型 | API | 说明 |
|------|------|-----|------|
| `seed18` | `ep-20260116160300-kq8ft` | ARK (豆包) | Seed1.8，DAG 框架推理 |
| `gpt41` | `gpt-4.1-2025-04-14` | AzureOpenAI (GPT Proxy) | GPT-4.1，DAG 框架推理 |

> **注意**：GPT Proxy (`search.bytedance.net`) 需要 `AzureOpenAI` 客户端，`step2_run_eval.py` 中通过检测 `api_base` 自动切换为 `AzureOpenAIServerModel` 子类。

---

## Benchmark 数据

| 数据集 | 类别 | 条数 | 评估指标 | 来源 |
|--------|------|------|----------|------|
| `bc_en_50.jsonl` | 通用 | 50 | Accuracy | BrowseComp EN |
| `bc_zh_50.jsonl` | 通用 | 50 | Accuracy | BrowseComp ZH |
| `dsq_50.jsonl` | 通用 | 50 | F1 | DeepSearchQA |
| `bc_en_med_30.jsonl` | 医疗 | 30 | Accuracy | BrowseComp Medical（来自 exp6） |
| `dsq_med_30.jsonl` | 医疗 | 30 | F1 | DeepSearchQA Medical（来自 exp6） |
| `hle_med_30.jsonl` | 医疗 | 30 | Accuracy | HLE Biology/Medicine（来自 exp6） |

---

## 评测结果

### 通用 Benchmarks（3-way 对比）

| Dataset | SWALM(seed18) | DAG(seed18) | DAG(gpt41) |
|---------|:---:|:---:|:---:|
| BrowseComp EN | **81.0%** | 28.0% | 20.0% |
| BrowseComp ZH | **70.0%** | 21.7%* | 16.0% |
| DeepSearchQA (F1) | 46.5% | **57.7%** | 45.4% |

\* bc_zh 只评了23条（用户确认足够）

### 医疗 Benchmarks（2-way 对比）

| Dataset | DAG(seed18) | DAG(gpt41) |
|---------|:---:|:---:|
| BrowseComp Medical | **23.3%** | 13.3% |
| DeepSearchQA Medical (F1) | 47.1% | **49.6%** |
| HLE Biology/Medicine | **43.3%** | 20.0% |

---

## 关键发现

### 1. BrowseComp 上 DAG 大幅落后 SWALM（↓53pp）
**根因：Context 爆炸**。DAG 框架无历史压缩机制，多跳复杂推理场景下：
- 平均 40+ 步
- 单题 input tokens 超过 800k
- SWALM 有 `CascadedFIFOCondenser`（max 20 history items）避免了此问题

### 2. DeepSearchQA 上 DAG(seed18) 反超 SWALM（57.7% vs 46.5%）
开放式问答场景不需要超长多跳推理，DAG 的多路并行搜索有明显优势。

### 3. GPT-4.1 整体不如 seed18
6 个数据集中，gpt41 只在 DSQ Medical（49.6% vs 47.1%）略胜，其余均落后。在 HLE Medical 上差距最大（20% vs 43.3%），说明 seed18 在医学专业知识上有显著优势。

### 4. 推理效率对比
| 模型×数据集 | 总耗时 | 平均/题 |
|------------|--------|---------|
| seed18 × dsq | ~1h56m | ~2.3min |
| gpt41 × dsq | ~51min | ~1.0min |
| seed18 × hle_med | ~33min | ~1.1min |
| gpt41 × hle_med | ~24min | ~0.8min |

---

## 产出文件

### 推理结果
```
assets/output/
├── seed18_bc_en.jsonl      (50条)
├── seed18_bc_zh.jsonl      (23条)
├── seed18_dsq.jsonl        (50条，含重复共100行，取前50)
├── seed18_bc_en_med.jsonl  (30条)
├── seed18_dsq_med.jsonl    (30条)
├── seed18_hle_med.jsonl    (30条)
├── gpt41_bc_en.jsonl       (50条)
├── gpt41_bc_zh.jsonl       (50条)
├── gpt41_dsq.jsonl         (50条)
├── gpt41_bc_en_med.jsonl   (30条)
├── gpt41_dsq_med.jsonl     (30条)
└── gpt41_hle_med.jsonl     (30条)
```

### 评分结果
```
assets/output/scored/
├── {model}_{dataset}_scored.jsonl   # 每条题目的评分细节
└── {model}_{dataset}_summary.json  # 汇总指标
```

### 可视化报告
`assets/output/exp2_dag_eval_report.html`
- 已部署到：https://data-edu.bytedance.net/proxy/gradio/host/[2605:340:cd51:602:6099:a9bf:69e2:3767]:10028/exp2_dag_eval.html

---

## 优化方向

1. **为 DAG 加历史压缩**（最高优先级）：参考 SWALM 的 `CascadedFIFOCondenser`，限制历史窗口大小，解决 BrowseComp 上的 Context 爆炸问题
2. **并行搜索策略调优**：DAG 在 DSQ 上的优势来自多路并行，可进一步优化 DAG 规划的分支策略
3. **医疗领域专项优化**：seed18 在 HLE Medical 上的强表现（43.3%）说明医学知识增强有效；gpt41 的落后可能是 system prompt 未针对医学优化
4. **更大规模评测**：当前只评了 23-50 条，建议扩展到完整数据集，提高统计置信度
5. **测试 seed16**：本次实验只测了 seed18，seed16 的对比数据缺失
