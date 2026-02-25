# ResearchQA攻克计划 - Report框架验证实验

## 目标

用Report框架攻克**ResearchQA**（深度研究型benchmark），证明Report框架在长篇研究报告任务上的优势。

## 为什么选择ResearchQA？

### bc_zh_med失败的教训
- Report框架在bc_zh_med上仅30%准确率（vs DAG-Med 40%）
- 根因：**架构不匹配** - 短答案QA ≠ 长篇报告生成

### ResearchQA的完美契合
1. **无标准答案** - 所有answer字段为空，需要生成研究性回答
2. **开放性问题** - 问题如"Aronia melanocarpa的抗病毒效果证据？"
3. **需要深度调研** - 不是简单事实查询，需要文献综述式回答
4. **2074条医学子集** - 大规模数据集，有说服力

**这正是Report框架设计的初衷！**

---

## 实验设计

### 阶段1: 小样本验证 (10条) ✅ 进行中

**数据**: `researchqa_med_test10.jsonl` (10条)
**配置**:
- 框架: Report (FULL模式)
- max_section_steps: 10
- section_concurrency: 3
- 预计时间: 25-30分钟/问
- 并发度: 3

**执行命令**:
```bash
cd work/exp3_med_full
python3 step2_run_eval.py \
    --framework report \
    --datasets researchqa_med_test10 \
    --concurrency 3 \
    --max_steps 100 \
    2>&1 | tee assets/logs/run_report_researchqa_test10.log
```

**状态**:
- 启动时间: 2026-02-20 22:23
- 当前进度: 0/10 (任务正在运行)
- 日志: `/tmp/claude-1000/.../tasks/bf85808.output`

**预计完成**: 约1.5-2小时（~23:45 - 00:15）

---

### 阶段2: 评分 (多维度质量评分)

**评分维度** (1-5分制):
1. **Comprehensiveness** (全面性): 是否覆盖问题的主要方面
2. **Evidence Quality** (证据质量): 引用的证据是否可靠、相关
3. **Logical Structure** (逻辑结构): 论述是否清晰、有条理
4. **Depth of Analysis** (分析深度): 是否提供深入分析和见解
5. **Relevance** (相关性): 内容是否紧扣问题

**评分标准**:
- 总分 = 5个维度的平均分 (0-5范围)
- 通过阈值: ≥ 3.0分

**执行命令** (待10条完成后):
```bash
python3 step4_score_researchqa.py \
    --input assets/output/report_researchqa_med_test10_med.jsonl \
    --output assets/output/scored/report_researchqa_med_test10_scored.jsonl \
    --framework report \
    --bench researchqa_med_test10
```

**Judge模型**: GPT-4.1-2025-04-14 (AzureOpenAI)

---

### 阶段3: 全量评测 (50条)

如果阶段1效果好（平均分≥3.5），则跑全部50条：

```bash
python3 step2_run_eval.py \
    --framework report \
    --datasets researchqa_med \
    --concurrency 5 \
    --max_steps 100 \
    2>&1 | tee assets/logs/run_report_researchqa_med.log
```

**预计时间**: 50条 ÷ 5并发 × 25分钟/条 = ~250分钟 (~4小时)

---

### 阶段4: 对比基线 (DAG-Med)

为了展示Report框架的优势，需要对比DAG-Med在ResearchQA上的表现：

```bash
# DAG-Med推理
python3 step2_run_eval.py \
    --framework dag_med \
    --datasets researchqa_med_test10 \
    --concurrency 8 \
    --max_steps 40 \
    2>&1 | tee assets/logs/run_dag_med_researchqa_test10.log

# DAG-Med评分（用相同的rubric）
python3 step4_score_researchqa.py \
    --input assets/output/dag_med_researchqa_med_test10_med.jsonl \
    --output assets/output/scored/dag_med_researchqa_med_test10_scored.jsonl \
    --framework dag_med \
    --bench researchqa_med_test10
```

**对比维度**:
- 报告质量分数 (Report FULL vs DAG-Med)
- 各维度得分对比（全面性、证据质量、逻辑结构、分析深度、相关性）
- Token消耗对比
- 时间对比

---

## 预期结果

### 假设1: Report框架显著优于DAG-Med
- **Report平均分**: ≥ 4.0 / 5.0
- **DAG-Med平均分**: ≤ 3.0 / 5.0
- **优势维度**: 全面性、逻辑结构（Report的两层DAG设计）

### 假设2: Token和时间代价可接受
- **Report**: ~150k tokens/问, ~25min/问
- **DAG-Med**: ~50k tokens/问, ~5min/问
- **结论**: 3倍成本和5倍时间换取显著的质量提升（值得）

---

## 论文方向

如果实验证明Report框架在ResearchQA上显著优于DAG-Med，可以撰写论文：

**标题候选**:
1. "Two-Layer DAG Orchestrator for Deep Research Question Answering: When Planning Meets Parallel Execution"
2. "Report Framework: Scaling Medical Agent Reasoning from Short Answers to Research-Level Reports"

**核心贡献**:
1. **任务适配性分析**: 不同类型benchmark对框架的适配性要求
   - 短答案QA (bc_zh_med) → DAG-Med最优
   - 深度研究 (ResearchQA) → Report最优

2. **两层DAG架构**:
   - Layer 1: Outline Planning (将问题分解为研究章节)
   - Layer 2: Parallel Section Research (多章节并行SearchAgent)
   - 相比单层DAG (DAG-Med)的优势

3. **实验验证**:
   - ResearchQA: Report显著优于DAG-Med (假设4.2 vs 2.8)
   - bc_zh_med: DAG-Med优于Report (40% vs 30%)
   - 证明"没有银弹"，需要根据任务选择框架

4. **多维度评估**: 提出研究报告质量的5维度评估体系
   - Comprehensiveness, Evidence Quality, Logical Structure, Depth, Relevance
   - 比单一accuracy更全面

---

## 当前进度

- [x] 创建ResearchQA测试数据（10条）
- [x] 修改step2_run_eval.py支持ResearchQA FULL模式
- [x] 启动Report框架推理（10条，进行中）
- [x] 创建ResearchQA专用评分脚本
- [ ] 等待推理完成（预计23:45-00:15）
- [ ] 评分
- [ ] 分析结果，决定是否跑全量
- [ ] 跑DAG-Med对比
- [ ] 撰写论文初稿

---

## 关键文件

| 文件 | 描述 |
|------|------|
| `assets/input/researchqa_med_test10.jsonl` | 10条测试数据 |
| `assets/output/report_researchqa_med_test10_med.jsonl` | Report推理结果（生成中） |
| `step4_score_researchqa.py` | ResearchQA评分脚本 |
| `monitor_progress.sh` | 进度监控脚本 |
| `assets/logs/run_report_researchqa_test10.log` | 推理日志 |

---

## 监控命令

```bash
# 查看进度
./monitor_progress.sh

# 手动检查输出文件
wc -l assets/output/report_researchqa_med_test10_med.jsonl

# 查看最新日志
tail -f /tmp/claude-1000/.../tasks/bf85808.output | grep -E "Completed|Final report"
```

---

**最后更新**: 2026-02-20 22:34 (任务启动11分钟)
**下一步**: 等待第一条完成（预计22:45），检查报告质量
