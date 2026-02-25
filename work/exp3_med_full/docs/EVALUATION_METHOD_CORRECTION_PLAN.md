# 评估方法纠正计划

**创建时间**: 2026-02-23 11:00
**问题**: 当前实验使用了错误的评估方法
**解决方案**: 使用官方仓库和X-EvalSuit的评估代码

---

## 🔍 问题诊断

### 当前错误的评估方法

| Benchmark | 官方评估方法 | 我的错误方法 | 影响 |
|-----------|------------|------------|------|
| ResearchQA | ResearchRubrics (任务特定rubrics) | 5维度通用评分 | ❌ 结果无法对比 |
| DRB | RACE (4维度+reference对比) + FACT (引用验证) | 5维度通用评分 | ❌ 结果无法对比 |
| DRB2 | Binary Rubric (3维度，41项细项) | Binary Rubric (正确) | ✅ 结果可信 |

---

## 📚 从X-EvalSuit学到的正确方法

### 1. DRB评估架构（来自 `agentic_eval/judger/drb.py`）

**双框架评估**：

#### RACE框架（报告质量）
```python
# 4个维度，每个0-10分
dimensions = {
    "comprehensiveness": 0-10,     # 全面性
    "insight": 0-10,                # 洞察力/分析深度
    "instruction_following": 0-10,  # 指令遵循
    "readability": 0-10             # 可读性
}

# ⚠️ 官方RACE需要与reference article对比！
# X-EvalSuit提供了简化版point-wise评估（无reference）
# 但注释明确指出：Official RACE requires reference comparison
```

#### FACT框架（引用准确性）
```python
# 评估流程
1. extract: 从报告中提取 (statement, URL) 对
2. deduplicate: 去除重复声明
3. scrape: 抓取URL内容
4. validate: 使用LLM验证引用是否支撑声明

# 输出指标
{
    "citation_accuracy": supported / (supported + unsupported),
    "effective_citations": 平均有效引用数
}
```

**关键代码位置**：
- 数据加载: `/mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/X-EvalSuit/agentic_eval/datasets/drb.py`
- Judger: `/mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/X-EvalSuit/agentic_eval/judger/drb.py`

---

## ✅ 正确的评估方案

### 方案A：使用官方DRB仓库（推荐，最权威）

#### 步骤1: Clone官方DRB仓库
```bash
cd /mnt/bn/med-mllm-lfv2/linjh/project/learn/2026_q1/eval/dag-deepresearch/work/exp3_med_full
git clone https://github.com/Ayanami0730/deep_research_bench.git official_repos/deep_research_bench
```

#### 步骤2: 准备环境和API密钥
```bash
cd official_repos/deep_research_bench
pip install -r requirements.txt

# 设置API密钥（需要Gemini和Jina API）
export GEMINI_API_KEY="your_gemini_key"
export JINA_API_KEY="your_jina_key"
```

#### 步骤3: 转换我们的输出为DRB格式
```python
# 使用X-EvalSuit的format_for_drb函数
from agentic_eval.judger.drb import format_for_drb

# 转换我们的report输出
formatted_data = []
for item in our_results:
    formatted = format_for_drb({
        "id": item["task_id"],
        "problem": item["question"],
        "final_response": item["agent_result"],
        "conversation_history": []  # 需要从traces中构建
    })
    formatted_data.append(formatted)

# 保存为JSONL
with open("data/test_data/raw_data/report_drb.jsonl", "w") as f:
    for item in formatted_data:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
```

#### 步骤4: 运行官方RACE评估
```bash
python -u deepresearch_bench_race.py report_drb \
    --raw_data_dir data/test_data/raw_data \
    --max_workers 10 \
    --query_file data/prompt_data/query.jsonl \
    --output_dir results/race/report_drb
```

#### 步骤5: 运行官方FACT评估
```bash
# Extract citations
python -u -m utils.extract \
    --raw_data_path data/test_data/raw_data/report_drb.jsonl \
    --output_path results/fact/report_drb/extracted.jsonl \
    --query_data_path data/prompt_data/query.jsonl \
    --n_total_process 10

# Deduplicate
python -u -m utils.deduplicate \
    --raw_data_path results/fact/report_drb/extracted.jsonl \
    --output_path results/fact/report_drb/deduplicated.jsonl \
    --query_data_path data/prompt_data/query.jsonl \
    --n_total_process 10

# Scrape URLs
python -u -m utils.scrape \
    --raw_data_path results/fact/report_drb/deduplicated.jsonl \
    --output_path results/fact/report_drb/scraped.jsonl \
    --n_total_process 10

# Validate
python -u -m utils.validate \
    --raw_data_path results/fact/report_drb/scraped.jsonl \
    --output_path results/fact/report_drb/validated.jsonl \
    --query_data_path data/prompt_data/query.jsonl \
    --n_total_process 10

# Statistics
python -u -m utils.stat \
    --input_path results/fact/report_drb/validated.jsonl \
    --output_path results/fact/report_drb/fact_result.txt
```

---

### 方案B：使用X-EvalSuit的简化版RACE（快速，但不官方）

#### 优点
- 不需要Gemini/Jina API密钥
- 不需要reference article
- 可以快速本地评估

#### 缺点
- **不是官方RACE方法**
- 结果与官方leaderboard不可比
- 缺少FACT框架的完整引用验证

#### 使用方法
```python
# 直接使用X-EvalSuit的DRBJudger
import sys
sys.path.append('/mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/X-EvalSuit')

from agentic_eval.judger.drb import DRBJudger
from llm_client import get_llm_client

# 初始化judger
llm_client = get_llm_client("gpt-4.1")  # 用于RACE评估
judger = DRBJudger(llm_client=llm_client)

# 评估单个报告
is_correct, judge_result = judger.judge(
    question=item["question"],
    response=item["agent_result"],
    correct_answer="",  # DRB没有ground truth
    full_traces={},  # 需要构建
    conversation_history=[]
)

# judge_result包含:
# - race: {comprehensiveness, insight, instruction_following, readability, overall}
# - fact: {num_citations, num_unique_urls, article_length}
```

---

### 方案C：结合方案（推荐用于论文）

1. **对DRB使用官方RACE+FACT评估**（权威结果）
2. **对ResearchQA暂时使用简化评估**（后续改进）
3. **保持DRB2的Rubric评估**（已经正确）

---

## 📋 具体实施步骤

### Phase 1: 准备工作（1天）

- [ ] Clone官方DRB仓库
- [ ] 设置Gemini和Jina API密钥（或申请测试密钥）
- [ ] 理解官方评估脚本的输入输出格式

### Phase 2: 数据转换（0.5天）

- [ ] 将我们的DRB报告转换为官方格式
- [ ] 构建conversation_history用于引用提取
- [ ] 验证转换后的数据格式正确

### Phase 3: 运行官方评估（0.5天）

- [ ] 运行RACE评估（预计20分钟）
- [ ] 运行FACT评估（预计30分钟）
- [ ] 解析结果并与当前结果对比

### Phase 4: 更新文档和代码（0.5天）

- [ ] 创建官方评估脚本wrapper
- [ ] 更新实验文档说明评估方法
- [ ] 生成新的对比HTML报告

---

## ⚠️ 关键问题和风险

### 1. API密钥问题
- **Gemini API**: 官方RACE需要Gemini-2.5-Pro
- **Jina API**: FACT框架的URL scraping需要
- **解决**: 申请API密钥或使用替代方案

### 2. Reference Article缺失
- **问题**: 官方RACE需要与reference article对比
- **影响**: 如果没有reference，只能用简化版point-wise评估
- **解决**: 查看DRB数据集是否包含reference article

### 3. ResearchQA评估
- **问题**: ResearchQA没有官方仓库的评估脚本
- **现状**: 只能使用简化评估或手动标注rubrics
- **建议**: 在论文中诚实说明使用了简化评估

---

## 🎯 优先级建议

### 高优先级（必须做）
1. ✅ **DRB2保持当前Rubric评估**（已经正确）
2. 🔴 **DRB使用官方RACE+FACT评估**（论文核心结果）

### 中优先级（建议做）
3. 🟡 **ResearchQA寻找官方评估方法**（提升可信度）

### 低优先级（可选）
4. 🟢 **创建统一的评估pipeline**（便于未来实验）

---

## 📊 预期结果对比

### DRB当前结果 vs 官方评估预期

| 指标 | 当前错误方法 | 官方RACE预期 | 差异 |
|------|------------|------------|------|
| Comprehensiveness | 4.78/5.0 (95.6%) | ? / 10 (转换为0-1归一化) | 未知 |
| Insight/Depth | 4.49/5.0 (89.8%) | ? / 10 | 未知 |
| Instruction Following | N/A | ? / 10 | 缺失 |
| Readability | 4.97/5.0 (99.4%) | ? / 10 | 未知 |
| Citation Accuracy | N/A | ? % | **完全缺失** |
| Effective Citations | N/A | ? 个 | **完全缺失** |

**重要**: 当前的5维度评分**无法转换**为官方RACE分数，必须重新评估！

---

## 💡 论文撰写建议

### 诚实说明评估方法

**错误做法** ❌:
> "We evaluated our system on DRB and achieved 3.50/5.0 average score."

**正确做法** ✅:
> "We evaluated our system on DRB using a simplified point-wise quality assessment (4 dimensions: comprehensiveness, insight, instruction-following, readability). While this differs from the official RACE framework which requires reference article comparison, our results show strong performance across all dimensions (avg 4.5/5.0). Official RACE+FACT evaluation is planned for future work."

或者（如果完成了官方评估）:
> "We evaluated our system on DRB using the official RACE and FACT frameworks. Our system achieved [X/10] in comprehensiveness, [Y%] citation accuracy, demonstrating [analysis]."

---

## 📚 参考资源

### 官方仓库
- DRB: https://github.com/Ayanami0730/deep_research_bench
- DRB2: https://github.com/imlrz/DeepResearch-Bench-II

### X-EvalSuit代码
- DRB Judger: `/mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/X-EvalSuit/agentic_eval/judger/drb.py`
- DRB Dataset: `/mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/X-EvalSuit/agentic_eval/datasets/drb.py`

### 论文
- DRB论文: https://arxiv.org/abs/2506.11763
- DRB2论文: https://arxiv.org/html/2601.08536
- ResearchRubrics: https://arxiv.org/html/2511.07685v1

---

**下一步**: 决定是否立即实施官方评估，还是先在论文中诚实说明当前使用的简化评估方法。
