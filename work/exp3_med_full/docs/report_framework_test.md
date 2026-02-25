# Report框架测试实验报告

## 实验概述

本实验测试了 **ReportOrchestrator** 作为第5个推理框架在医学benchmark评测中的表现。ReportOrchestrator是一个两层DAG架构，专为生成结构化研究报告设计。

**测试时间**: 2026-02-20
**测试数据集**: bc_zh_med (30个医学问题，中文浏览查询任务)
**测试深度**: ULTRA-LITE模式（轻量化配置）
**对比基线**: DAG-Med框架 (40% accuracy, 25k tokens/question)

---

## 一、ReportOrchestrator架构说明

### 1.1 两层DAG设计

ReportOrchestrator采用**两层DAG**架构：

```
Layer 1 (Outline Planning):
    Question → OutlinePlanner → [Section1, Section2, ..., SectionN]
                                        ↓
Layer 2 (Parallel Research):
    Section1 → SearchAgent (max_steps=3, tools=[web_search, browsing])
    Section2 → SearchAgent (max_steps=3, tools=[web_search, browsing])
    ...
    SectionN → SearchAgent (max_steps=3, tools=[web_search, browsing])
                                        ↓
    Final Report Assembly → "## Final Answer: {answer}"
```

**关键特点**:
- **Layer 1**: OutlinePlanner将问题分解为3-8个研究章节
- **Layer 2**: 每个章节由独立的SearchAgent并行搜索（max_concurrency=8）
- **最终汇总**: 将所有章节研究结果整合为完整报告

### 1.2 三种深度模式

| 模式 | max_section_steps | section_concurrency | 适用场景 | 预计时间/问 |
|------|------------------|---------------------|---------|------------|
| **FULL** | 10 | 3 | 详细报告，复杂问题 | ~30分钟 |
| **LITE** | 5 | 5 | 中等深度研究 | ~15分钟 |
| **ULTRA-LITE** | 3 | 8 | 快速验证，QA任务 | ~5-8分钟 |

本实验采用**ULTRA-LITE**模式，优化速度以适应评测场景。

---

## 二、实验结果

### 2.1 整体表现

| 指标 | 数值 |
|-----|------|
| **准确率** | 30.0% (9/30) |
| **平均时间/问** | ~2.7分钟 |
| **平均tokens/问** | ~85,000 |
| **总推理时间** | 82分钟 (30问) |

### 2.2 对比分析

| 框架 | 准确率 | Tokens/问 | 相对性能 |
|------|--------|----------|---------|
| **DAG-Med** | 40.0% | ~25,000 | 基线 |
| **Report (ULTRA-LITE)** | 30.0% | ~85,000 | -10% / +3.4× |

**结论**: Report框架准确率**降低10个百分点**，token消耗**增加3.4倍**。

### 2.3 典型错误案例

#### 案例1：过度推理 vs 简单事实
- **问题**: "法国医生最初从何处了解到这种治疗手段？"
- **正确答案**: 电视
- **Report回答**: "The French doctor initially learned about the treatment through Sino-French academic exchanges..."
- **问题**: 生成长篇英文学术分析，未能定位简单中文事实答案

#### 案例2：信息不足判断
- **问题**: "患者长时间躺在床上却总感觉疲惫...这个'修复思考之钥'分子被批准的日期是？"
- **正确答案**: 2014/8/13
- **Report回答**: "Insufficient information to determine the approval date..."
- **问题**: ULTRA-LITE模式仅3步搜索，未能深入查找具体日期信息

---

## 三、根因分析

### 3.1 架构不匹配

**ReportOrchestrator的设计目标**：
- 生成**长篇结构化报告**（3000-10000字）
- 适合**开放性研究问题**
- 强调**全面性和完整性**

**bc_zh_med的任务特点**：
- 需要**短答案**（1-5个词/数字）
- 要求**精确定位事实**（日期、名称、数字）
- 强调**准确性和简洁性**

**架构冲突**：
- Report倾向于生成长篇英文分析 → 中文短答案提取困难
- 两层DAG增加复杂度 → 引入更多错误可能
- Outline分解可能导致问题焦点分散

### 3.2 ULTRA-LITE模式的局限

- 每章节仅3步搜索 → 可能miss关键信息
- 21个错误案例中，约40%是"Insufficient information"类型
- 说明轻量化导致信息获取不足

---

## 四、结论与建议

### 4.1 核心结论

**Report框架不适合用于医学benchmark的QA评测任务**，主要原因：

1. **准确率劣势**：30% vs 40% (DAG-Med)，下降25%
2. **成本劣势**：85k tokens/q vs 25k tokens/q，增加3.4倍
3. **架构不匹配**：报告生成 ≠ 短答案QA

### 4.2 适用场景建议

**Report框架更适合**：
- 长篇研究报告任务（如"分析COVID-19疫苗发展历程"）
- 多维度综合分析（如"比较三种治疗方案的优劣"）
- 结构化文档生成（如医学综述、案例分析）

**不适合**：
- 短答案QA（如MedQA, MMLU-Med）
- 数值/日期精确定位任务
- 快速事实查询

---

## 五、数据产出

### 5.1 文件清单

| 文件路径 | 描述 |
|---------|------|
| `assets/output/report_bc_zh_med.jsonl` | 30个问题的推理结果 |
| `assets/output/scored/report_bc_zh_med_scored.jsonl` | 评分后的详细结果 |
| `assets/output/scored/report_bc_zh_med_summary.json` | 准确率汇总 |
| `assets/logs/run_report_bc_zh_med.log` | 推理日志 |
| `assets/logs/score_report_bc_zh_med.log` | 评分日志 |

---

**文档版本**: v1.0
**最后更新**: 2026-02-20
**作者**: Claude Sonnet 4.5
