# exp4_report_drb: DRB评估对齐 + Report框架全面优化

## 目标
1. 彻底对齐官方RACE评估：使用reference-based评分（分数=target/(target+ref)）
2. 全面优化Report框架：从Prompt、架构参数、搜索工具、引用格式、合成质量等多维度优化

## 执行步骤
1. step1: baseline RACE评估（用exp3结果）
2. step2: 优化prompt + 重新推理50条
3. step3: 对新结果跑RACE评估
4. step4: 对比分析 + 可视化
