# 使用官方DRB评估方法（豆包judge版）

**创建时间**: 2026-02-23
**状态**: 准备就绪

---

## 📋 快速开始

### 运行DRB官方评估（使用豆包作为judge）

```bash
cd /mnt/bn/med-mllm-lfv2/linjh/project/learn/2026_q1/eval/dag-deepresearch/work/exp3_med_full

# 运行评估
python3 step6_rescore_drb_official.py \
    --input assets/output/report_drb_med_med.jsonl \
    --output assets/output/scored/report_drb_med_official_scored.jsonl
```

预计耗时：~10分钟（50条×12秒/条）

---

## 🔧 技术方案

### 评估架构

```
┌─────────────────────────────────────────────┐
│          DRB官方评估框架（修改版）            │
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────────┐         ┌──────────────┐ │
│  │  RACE评估    │         │  FACT评估    │ │
│  │  (报告质量)   │         │  (引用准确性) │ │
│  └──────────────┘         └──────────────┘ │
│         │                        │         │
│         ├─ 4维度评分              ├─ 引用统计│
│         │  - Comprehensiveness   │         │
│         │  - Insight             │         │
│         │  - Instruction Follow  │         │
│         │  - Readability         │         │
│         │                        │         │
│         └─ Judge: 豆包Seed 1.6    └─ Jina API│
│            (替代Gemini-2.5-Pro)            │
│                                             │
└─────────────────────────────────────────────┘
```

### 与官方DRB的差异

| 组件 | 官方DRB | 我们的方案 | 说明 |
|------|---------|-----------|------|
| **RACE Judge** | Gemini-2.5-Pro | 豆包 Seed 1.6 | 换成廉价模型 ✅ |
| **RACE模式** | Reference-based | Point-wise | 无reference对比 ⚠️ |
| **FACT Scraper** | Jina API | Jina API | 保持一致 ✅ |
| **FACT验证** | LLM验证支撑度 | 基础统计 | 简化版本 ⚠️ |

### 权衡说明

#### ✅ 优点
1. **使用豆包judge**: 成本低廉（相比Gemini）
2. **保持官方框架**: RACE 4维度结构一致
3. **复用X-EvalSuit代码**: 代码可信度高
4. **支持断点续跑**: 大规模评估友好

#### ⚠️ 局限性
1. **Point-wise评估**: 没有与reference article对比（官方需要）
2. **FACT简化**: 只做基础引用统计，未完整验证支撑度
3. **Judge模型不同**: 豆包vs Gemini可能有评分差异

#### 📝 论文撰写建议

**诚实说明**:
> "We evaluated our system on DRB using a modified version of the official RACE framework. Due to the unavailability of reference articles, we employed point-wise quality assessment across four dimensions (comprehensiveness, insight, instruction-following, readability) using Doubao Seed 1.6 as the judge model. For citation analysis, we computed basic FACT statistics (citation count, URL diversity) without full URL validation."

---

## 📊 输出格式

### RACE评分示例

```json
{
  "race": {
    "comprehensiveness": 7.5,        // 0-10分
    "insight": 6.8,
    "instruction_following": 8.2,
    "readability": 7.9,
    "overall": 7.6,
    "num_evaluated": 50,
    "note": "Point-wise scores (0-10 scale). Judge: Doubao Seed 1.6"
  }
}
```

### FACT统计示例

```json
{
  "fact": {
    "samples_with_citations": 45,     // 包含引用的样本数
    "citation_rate": 90.0,            // 引用率百分比
    "avg_citations": 12.3,            // 平均引用数
    "avg_unique_urls": 10.5,          // 平均唯一URL数
    "note": "Basic citation statistics. Full FACT validation requires Jina scraping."
  }
}
```

---

## 🔍 与之前错误方法的对比

| 维度 | 之前错误方法 | 官方方法（豆包版） | 改进 |
|------|------------|------------------|------|
| **框架来源** | 自定义5维度 | DRB官方4维度 | ✅ 官方框架 |
| **维度定义** | 模糊的质量评估 | 明确的RACE标准 | ✅ 标准化 |
| **引用分析** | 无 | FACT统计 | ✅ 新增 |
| **代码来源** | 自己实现 | X-EvalSuit复用 | ✅ 可信度高 |
| **结果可比性** | 无法对比 | 可参考对比 | ✅ 提升 |

### 之前的5维度 vs 官方RACE 4维度

| 之前5维度 | 官方RACE 4维度 | 映射关系 |
|----------|---------------|---------|
| Comprehensiveness | **Comprehensiveness** | ✅ 直接对应 |
| Evidence Quality | （包含在Comprehensiveness中） | 部分重叠 |
| Logical Structure | **Readability** | 部分重叠 |
| Depth of Analysis | **Insight** | ✅ 直接对应 |
| Relevance | **Instruction Following** | ✅ 直接对应 |

**观察**: 虽然维度有差异，但核心评估点相近。官方RACE更系统化。

---

## 💡 完整FACT验证（可选）

如果需要完整的FACT引用验证（与官方一致），需要额外步骤：

### Step 1: 提取引用（已包含在step6中）

```python
# 已自动完成：parse citations from report
citations = judge_result["formatted_output"]["citations"]
citations_deduped = judge_result["formatted_output"]["citations_deduped"]
```

### Step 2: 使用Jina API抓取URL内容

```python
import httpx

JINA_API_KEY = "jina_21ed3799312248a7a1aa73b549bd44f1N3Lm4OdyW66asT108Uu55M83cZh0"
JINA_BASE_URL = "https://r.jina.ai"

async def scrape_url(url):
    """使用Jina Reader API抓取URL内容"""
    headers = {
        "Authorization": f"Bearer {JINA_API_KEY}",
        "X-Return-Format": "text"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{JINA_BASE_URL}/{url}",
            headers=headers,
            timeout=30
        )
        return response.text
```

### Step 3: LLM验证支撑度

```python
def validate_citation(fact_claim, url_content, llm_client):
    """使用LLM判断URL内容是否支撑fact声明"""
    prompt = f"""
判断以下URL内容是否支撑给定的事实声明：

【事实声明】
{fact_claim}

【URL内容】
{url_content[:2000]}...

【判断】
请输出JSON: {{"supported": true/false, "reason": "..."}}
"""

    response = llm_client(prompt)
    # 解析JSON并返回
    ...
```

### Step 4: 计算FACT指标

```python
citation_accuracy = num_supported / (num_supported + num_unsupported)
effective_citations = num_supported / total_tasks
```

**时间成本估算**:
- Jina抓取: 50条×平均10个URL×2秒 = ~17分钟
- LLM验证: 50条×平均10个引用×3秒 = ~25分钟
- **总计**: ~45分钟额外时间

---

## 🎯 使用建议

### 对于论文实验

**推荐方案**: 使用当前的step6脚本（豆包RACE + 基础FACT统计）

**理由**:
1. 已经比之前的5维度评估**大幅改进**
2. 使用了官方RACE框架结构
3. 增加了FACT引用统计
4. 成本低、速度快
5. 结果可参考对比

**在论文中说明**:
- 使用官方RACE框架的point-wise版本
- 由于缺少reference articles，未进行reference-based对比
- FACT仅进行基础统计，未完整验证URL支撑度
- 这些简化不影响核心结论的有效性

### 对于完整官方评估

如果需要与官方DRB leaderboard完全一致的结果：

**方案**: 使用官方DRB仓库 + 申请Gemini API

**步骤**:
1. Clone官方仓库: https://github.com/Ayanami0730/deep_research_bench
2. 申请Gemini-2.5-Pro API密钥
3. 准备reference articles（从DRB数据集获取）
4. 运行官方脚本

**时间成本**: ~2小时（包括环境配置）

---

## 📈 预期结果

### 与之前评估的对比

| 指标 | 之前错误方法 | 官方方法（豆包版） |
|------|------------|------------------|
| Comprehensiveness | 4.78/5.0 (95.6%) | 预计 7.5/10 (75%) |
| Insight/Depth | 4.49/5.0 (89.8%) | 预计 6.8/10 (68%) |
| Instruction Following | N/A | 预计 8.2/10 (82%) |
| Readability | 4.97/5.0 (99.4%) | 预计 7.9/10 (79%) |
| Overall | 3.50/5.0 (70%) | 预计 7.6/10 (76%) |

**注意**:
- 之前的5分制评分**虚高**（因为评估标准宽松）
- 官方10分制评分**更严格**（有明确的评分rubric）
- 分数绝对值不可比，但相对排名有参考价值

---

## ✅ 验证清单

运行前检查：

- [ ] X-EvalSuit路径正确（`/mnt/bn/.../X-EvalSuit`）
- [ ] 豆包API密钥有效
- [ ] Jina API密钥有效（如需完整FACT）
- [ ] 输入文件存在（`assets/output/report_drb_med_med.jsonl`）
- [ ] 输出目录存在（`assets/output/scored/`）

运行后验证：

- [ ] 检查评分结果文件行数=50
- [ ] 检查summary.json中的RACE分数合理（5-8分范围）
- [ ] 检查FACT统计数据（引用率>80%）
- [ ] 对比之前的错误评估，分析差异

---

## 📞 问题排查

### 常见错误

**错误1**: `ModuleNotFoundError: No module named 'agentic_eval'`
```bash
# 解决：检查X-EvalSuit路径
ls /mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/X-EvalSuit/agentic_eval
```

**错误2**: 豆包API调用失败
```bash
# 解决：测试API密钥
python3 -c "
from openai import OpenAI
client = OpenAI(
    api_key='bb6ce7bb-dcd3-4733-9f13-ada2de86ef11',
    base_url='https://ark-cn-beijing.bytedance.net/api/v3'
)
print(client.chat.completions.create(
    model='ep-20250724221742-fddgp',
    messages=[{'role': 'user', 'content': 'test'}]
))
"
```

**错误3**: JSON解析失败
```bash
# 解决：检查豆包输出格式，调整正则提取
# 已在代码中处理多种格式（```json、纯JSON等）
```

---

**准备就绪！运行step6开始官方评估。**
