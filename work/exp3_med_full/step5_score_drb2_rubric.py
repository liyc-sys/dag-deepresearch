#!/usr/bin/env python3
"""
DRB2 Rubric评分脚本

使用GPT-4.1作为Judge，根据每个任务的rubric标准逐项评分
Rubric包含三部分：
- info_recall: 信息召回（26项）
- analysis: 分析质量（11项）
- presentation: 呈现质量（4项）
"""
import json
import os
import logging
from openai import AzureOpenAI
from tqdm import tqdm
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Azure OpenAI配置（用于GPT-4.1 Judge）
AZURE_API_KEY = "f5CBx539CnpxCx0ylnAshe3mjJpd71Uk_GPT_AK"
AZURE_ENDPOINT = "https://search.bytedance.net/gpt/openapi/online/v2/crawl"
AZURE_DEPLOYMENT = "gpt-4.1-2025-04-14"
AZURE_API_VERSION = "2024-02-01"

DRB2_RUBRIC_JUDGE_PROMPT = """\
You are an expert judge evaluating a research report against specific rubric criteria.

**Task**: Assess if the report satisfies each rubric item.

**Rubric Categories**:
1. **Info Recall** (26 items): Does the report include specific facts, data, studies, or details?
2. **Analysis** (11 items): Does the report provide analytical insights, conclusions, or interpretations?
3. **Presentation** (4 items): Does the report follow required structural and formatting guidelines?

**Scoring Rules**:
- For each rubric item, assign **1** if satisfied, **0** if not satisfied
- Be strict but fair: the report must explicitly demonstrate the requirement
- Missing or incomplete information = 0 points
- Vague statements without specifics = 0 points

**Input Format**:
```
Question: {question}

Rubric Items:
{rubric_json}

Report:
{report}
```

**Output Format (JSON only)**:
{{
  "info_recall_scores": [1, 0, 1, ...],  # 26 scores
  "analysis_scores": [1, 1, 0, ...],     # 11 scores
  "presentation_scores": [1, 0, 1, ...], # 4 scores
  "info_recall_total": <sum of info_recall_scores>,
  "analysis_total": <sum of analysis_scores>,
  "presentation_total": <sum of presentation_scores>,
  "total_score": <sum of all scores>,
  "max_possible": 41,
  "pass_threshold": 33,
  "is_pass": <true if total_score >= 33 else false>,
  "overall_comment": "<1-2 sentence summary of strengths and weaknesses>"
}}

**Important**: Output ONLY valid JSON. No explanation before or after.
"""

def load_rubric_from_item(item):
    """从item的metadata中提取rubric"""
    metadata = item.get("metadata", {})
    rubric = metadata.get("rubric", {})

    if isinstance(rubric, str):
        try:
            rubric = json.loads(rubric)
        except Exception:
            logger.error(f"无法解析rubric字符串")
            return None

    if not isinstance(rubric, dict):
        logger.error(f"Rubric格式错误: {type(rubric)}")
        return None

    return rubric

def judge_with_rubric(question, report, rubric, client):
    """使用GPT-4.1 Judge根据rubric评分"""
    rubric_json = json.dumps(rubric, ensure_ascii=False, indent=2)

    user_prompt = f"""Question: {question}

Rubric Items:
{rubric_json}

Report:
{report}
"""

    try:
        response = client.chat.completions.create(
            model=AZURE_DEPLOYMENT,
            messages=[
                {"role": "system", "content": DRB2_RUBRIC_JUDGE_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=2000
        )

        result_text = response.choices[0].message.content.strip()

        # 尝试提取JSON（可能包含markdown代码块）
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()

        result = json.loads(result_text)
        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}")
        logger.error(f"原始输出: {result_text[:500]}")
        return None
    except Exception as e:
        logger.error(f"评分请求失败: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="DRB2 Rubric评分")
    parser.add_argument("--input", required=True, help="输入jsonl文件（包含agent_result）")
    parser.add_argument("--output", required=True, help="输出jsonl文件（包含rubric评分）")
    parser.add_argument("--framework", required=True, help="框架名称（如report）")
    parser.add_argument("--bench", required=True, help="Benchmark名称（如drb2_med）")
    args = parser.parse_args()

    logger.info(f"开始评分: {args.framework} × {args.bench}")
    logger.info(f"输入: {args.input}")
    logger.info(f"输出: {args.output}")

    # 初始化Azure OpenAI客户端
    client = AzureOpenAI(
        api_key=AZURE_API_KEY,
        api_version=AZURE_API_VERSION,
        azure_endpoint=AZURE_ENDPOINT
    )

    # 加载输入数据
    items = []
    with open(args.input, 'r') as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))

    # 读取已评分数据（支持断点续跑）
    scored_ids = set()
    if os.path.exists(args.output):
        with open(args.output, 'r') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if "rubric_score" in data:
                        scored_ids.add(data["task_id"])

    logger.info(f"总={len(items)}, 已评={len(scored_ids)}, 待评={len(items) - len(scored_ids)}")

    # 评分统计
    total_count = 0
    passed_count = 0
    total_score_sum = 0

    # 逐条评分
    with open(args.output, 'a') as out_f:
        for item in tqdm(items, desc="Scoring DRB2 reports"):
            task_id = item["task_id"]

            if task_id in scored_ids:
                # 跳过已评分
                continue

            question = item["question"]
            report = item.get("agent_result", "")
            rubric = load_rubric_from_item(item)

            if not rubric:
                logger.warning(f"任务 {task_id} 缺少rubric，跳过")
                continue

            if not report:
                logger.warning(f"任务 {task_id} 没有报告结果，跳过")
                continue

            # 调用Judge评分
            score_result = judge_with_rubric(question, report, rubric, client)

            if score_result is None:
                logger.error(f"任务 {task_id} 评分失败")
                # 写入失败标记
                item["rubric_score"] = None
                item["is_pass"] = False
            else:
                # 写入评分结果
                item["rubric_score"] = score_result
                item["is_pass"] = score_result.get("is_pass", False)

                # 统计
                total_count += 1
                if item["is_pass"]:
                    passed_count += 1
                total_score_sum += score_result.get("total_score", 0)

            # 保存结果
            out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
            out_f.flush()

    # 汇总结果
    summary = {
        "framework": args.framework,
        "bench": args.bench,
        "total": len(items),
        "evaluated": total_count,
        "passed": passed_count,
        "pass_rate": passed_count / total_count if total_count > 0 else 0.0,
        "avg_score": total_score_sum / total_count if total_count > 0 else 0.0,
        "max_possible": 41,
        "pass_threshold": 33
    }

    logger.info(f"  汇总: {summary}")

    # 保存汇总
    summary_path = args.output.replace("_scored.jsonl", "_summary.json")
    with open(summary_path, 'w') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info(f"  汇总已保存: {summary_path}")

    print("\n===== DRB2 Rubric评分结果 =====")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
