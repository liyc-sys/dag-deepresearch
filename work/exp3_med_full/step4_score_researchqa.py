#!/usr/bin/env python3
"""
ResearchQA专用评分脚本 - 使用LLM-as-judge对研究报告进行多维度质量评分

评分维度：
1. Comprehensiveness (全面性): 是否覆盖问题的主要方面
2. Evidence Quality (证据质量): 引用的证据是否可靠、相关
3. Logical Structure (逻辑结构): 论述是否清晰、有条理
4. Depth of Analysis (分析深度): 是否提供深入分析和见解
5. Relevance (相关性): 内容是否紧扣问题

总分计算: 5个维度平均分 (每维度1-5分)
"""

import json
import os
import re
from openai import AzureOpenAI
from tqdm import tqdm
import argparse
import logging

# GPT-4.1 Judge配置
GPT41_JUDGE_MODEL = "gpt-4.1-2025-04-14"
AZURE_API_KEY = "f5CBx539CnpxCx0ylnAshe3mjJpd71Uk_GPT_AK"  # 字节内部GPT代理
AZURE_API_BASE = "https://search.bytedance.net/gpt/openapi/online/v2/crawl"

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Judge Prompt
RESEARCHQA_JUDGE_PROMPT = """\
You are an expert evaluator assessing the quality of a research report. Evaluate the report on FIVE dimensions using a 1-5 scale:

**Evaluation Dimensions:**

1. **Comprehensiveness** (1-5)
   - Does the report cover all major aspects of the research question?
   - Are multiple perspectives or subtopics addressed?
   - Score 5: Comprehensive coverage of all key aspects
   - Score 1: Superficial, missing major aspects

2. **Evidence Quality** (1-5)
   - Are claims supported by credible evidence/sources?
   - Is the evidence relevant and specific?
   - Score 5: Strong, credible, well-cited evidence
   - Score 1: No evidence or unreliable sources

3. **Logical Structure** (1-5)
   - Is the report well-organized with clear sections?
   - Does the argumentation flow logically?
   - Score 5: Excellent structure, clear logical flow
   - Score 1: Disorganized, hard to follow

4. **Depth of Analysis** (1-5)
   - Does the report provide insightful analysis beyond surface facts?
   - Are mechanisms, relationships, or implications explored?
   - Score 5: Deep, insightful analysis with nuanced understanding
   - Score 1: Shallow, merely lists facts without analysis

5. **Relevance** (1-5)
   - Does the report stay focused on answering the specific question?
   - Is there unnecessary tangential information?
   - Score 5: Highly relevant, directly addresses the question
   - Score 1: Off-topic or vague

**Output Format (JSON only):**
{{
  "comprehensiveness": {{"score": <1-5>, "reason": "<brief explanation>"}},
  "evidence_quality": {{"score": <1-5>, "reason": "<brief explanation>"}},
  "logical_structure": {{"score": <1-5>, "reason": "<brief explanation>"}},
  "depth_of_analysis": {{"score": <1-5>, "reason": "<brief explanation>"}},
  "relevance": {{"score": <1-5>, "reason": "<brief explanation>"}}
}}

**Research Question:**
{question}

**Report to Evaluate:**
{report}
"""


def call_judge(prompt, max_retries=3):
    """调用GPT-4.1 Judge"""
    client = AzureOpenAI(
        api_key=AZURE_API_KEY,
        api_version="2024-02-01",
        azure_endpoint=AZURE_API_BASE,
        azure_deployment=GPT41_JUDGE_MODEL,
    )

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=GPT41_JUDGE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Judge调用失败 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return None
    return None


def judge_researchqa_report(item):
    """
    对单个ResearchQA报告进行多维度评分

    Args:
        item: dict包含question和agent_result (report)

    Returns:
        tuple: (overall_score, detail_dict)
            - overall_score: 5个维度的平均分 (0-5范围)
            - detail_dict: 包含各维度分数和理由的字典
    """
    question = item.get("question", "")
    report = item.get("report", item.get("agent_result", ""))

    if not report or not question:
        return 0.0, {"error": "missing question or report"}

    # 截断过长的报告（保留前8000字符）
    report_truncated = report[:8000]
    if len(report) > 8000:
        report_truncated += "\n\n[... report truncated ...]"

    prompt = RESEARCHQA_JUDGE_PROMPT.format(
        question=question[:500],
        report=report_truncated
    )

    raw = call_judge(prompt, max_retries=3)
    if not raw:
        return 0.0, {"error": "judge API call failed"}

    # 解析JSON
    try:
        # 清理markdown代码块
        raw_clean = re.sub(r'```(?:json)?\s*', '', raw).strip().rstrip('`')
        scores = json.loads(raw_clean)

        # 提取5个维度的分数
        dims = ["comprehensiveness", "evidence_quality", "logical_structure",
                "depth_of_analysis", "relevance"]

        total_score = 0
        parsed_scores = {}
        for dim in dims:
            if dim in scores and isinstance(scores[dim], dict):
                score = scores[dim].get("score", 0)
                reason = scores[dim].get("reason", "")
                parsed_scores[dim] = {"score": score, "reason": reason}
                total_score += score
            else:
                parsed_scores[dim] = {"score": 0, "reason": "parsing error"}

        # 计算平均分 (0-5范围)
        overall_score = total_score / len(dims) if dims else 0.0

        return overall_score, {
            "overall_score": overall_score,
            "dimensions": parsed_scores,
            "raw_response": raw
        }

    except Exception as e:
        logger.error(f"解析Judge结果失败: {e}")
        return 0.0, {"error": f"parsing failed: {str(e)}", "raw": raw}


def score_file(input_file, output_file):
    """
    对整个ResearchQA结果文件进行评分

    Args:
        input_file: 推理结果jsonl文件路径
        output_file: 评分后的输出jsonl文件路径
    """
    # 读取输入数据
    with open(input_file, 'r', encoding='utf-8') as f:
        data = [json.loads(line) for line in f if line.strip()]

    # 读取已评分数据（断点续跑）
    scored_ids = set()
    scored_data = []
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    scored_ids.add(item.get("task_id", ""))
                    scored_data.append(item)

    # 过滤待评分数据
    to_score = [item for item in data if item.get("task_id") not in scored_ids]

    logger.info(f"总={len(data)}, 已评={len(scored_ids)}, 待评={len(to_score)}")

    if not to_score:
        logger.info("全部已评分，跳过")
        return scored_data

    # 逐条评分
    for item in tqdm(to_score, desc="Scoring ResearchQA reports"):
        overall_score, detail = judge_researchqa_report(item)

        item["judge_result"] = {
            "overall_score": overall_score,
            "detail": detail,
            "is_correct": overall_score >= 3.0  # 3分及以上视为"通过"
        }

        scored_data.append(item)

        # 实时追加写入（断点续跑）
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    return scored_data


def compute_summary(scored_data, framework, bench):
    """
    计算汇总统计

    Returns:
        dict: 包含平均分、通过率等统计信息
    """
    if not scored_data:
        return {}

    overall_scores = [item["judge_result"]["overall_score"]
                     for item in scored_data
                     if "judge_result" in item]

    passed = sum(1 for item in scored_data
                 if item.get("judge_result", {}).get("is_correct", False))

    # 计算各维度平均分
    dims = ["comprehensiveness", "evidence_quality", "logical_structure",
            "depth_of_analysis", "relevance"]
    dim_avgs = {}
    for dim in dims:
        scores = [item["judge_result"]["detail"]["dimensions"][dim]["score"]
                 for item in scored_data
                 if "judge_result" in item
                 and "dimensions" in item["judge_result"].get("detail", {})
                 and dim in item["judge_result"]["detail"]["dimensions"]]
        dim_avgs[dim] = sum(scores) / len(scores) if scores else 0.0

    summary = {
        "framework": framework,
        "bench": bench,
        "total": len(scored_data),
        "passed": passed,
        "pass_rate": passed / len(scored_data) if scored_data else 0.0,
        "avg_overall_score": sum(overall_scores) / len(overall_scores) if overall_scores else 0.0,
        "dimension_averages": dim_avgs,
    }

    return summary


def main():
    parser = argparse.ArgumentParser(description="ResearchQA评分脚本")
    parser.add_argument("--input", required=True, help="推理结果文件路径")
    parser.add_argument("--output", required=True, help="评分输出文件路径")
    parser.add_argument("--framework", required=True, help="框架名称")
    parser.add_argument("--bench", required=True, help="Benchmark名称")
    args = parser.parse_args()

    if not AZURE_API_KEY:
        logger.error("AZURE_API_KEY环境变量未设置")
        return

    logger.info(f"开始评分: {args.framework} × {args.bench}")
    logger.info(f"输入: {args.input}")
    logger.info(f"输出: {args.output}")

    # 评分
    scored_data = score_file(args.input, args.output)

    # 计算汇总
    summary = compute_summary(scored_data, args.framework, args.bench)
    logger.info(f"  汇总: {summary}")

    # 保存汇总
    summary_file = args.output.replace("_scored.jsonl", "_summary.json")
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info(f"  汇总已保存: {summary_file}")

    # 打印结果
    print("\n===== ResearchQA评分结果 =====")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
