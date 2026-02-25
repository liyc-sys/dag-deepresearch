#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 3: 通用官方RACE评估脚本

整体逻辑:
1. 加载report结果文件（支持step2输出格式，也支持exp3格式）
2. 提取question字段作为匹配key, report字段作为target article
3. 加载官方reference.jsonl和criteria.jsonl，通过question==prompt匹配
4. 对每条问题：
   - 构建评分prompt（使用官方score_prompt_zh/en的generate_merged_score_prompt）
   - article_1=我们的report, article_2=reference article
   - 调用指定judge模型打分
   - 解析JSON，提取4维度评分
5. 调用calculate_weighted_scores计算加权分
6. 归一化: normalized = target_total / (target_total + reference_total)
7. 输出scored结果 + summary

用法:
  # 评估step2的v2 report
  python3 step3_race_eval.py --input assets/output/report_v2_drb_med.jsonl --tag v2
  # 评估baseline (exp3的结果)
  python3 step3_race_eval.py --input assets/input/exp3_report_drb_med_med.jsonl --tag baseline
"""

import os
import sys
import json
import time
import logging
import argparse
import concurrent.futures
import threading
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 路径
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
INPUT_DIR = ASSETS_DIR / "input"
OUTPUT_DIR = ASSETS_DIR / "output" / "scored"
DRB_DIR = BASE_DIR.parent / "exp3_med_full" / "official_repos" / "deep_research_bench"
ENV_PATH = Path(__file__).resolve().parents[3] / "0001_utils" / "api" / ".env"

# 必须先load_dotenv，DRB的utils/__init__.py会import api.py，里面需要JINA_API_KEY
load_dotenv(ENV_PATH)

# 导入官方工具
sys.path.insert(0, str(DRB_DIR))
from prompt.score_prompt_zh import generate_merged_score_prompt as zh_merged_score_prompt
from prompt.score_prompt_en import generate_merged_score_prompt as en_merged_score_prompt
from utils.score_calculator import calculate_weighted_scores
from utils.json_extractor import extract_json_from_markdown

MAX_RETRIES = 10


def load_jsonl(path: str) -> list:
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def save_jsonl(data: list, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def format_criteria_list(criteria_data: dict) -> str:
    criteria_for_prompt = {}
    for dim, criterions_list in criteria_data.get("criterions", {}).items():
        if not isinstance(criterions_list, list):
            continue
        criteria_for_prompt[dim] = []
        for crit_item in criterions_list:
            if isinstance(crit_item, dict) and "criterion" in crit_item and "explanation" in crit_item:
                criteria_for_prompt[dim].append({
                    "criterion": crit_item["criterion"],
                    "explanation": crit_item["explanation"]
                })
    return json.dumps(criteria_for_prompt, ensure_ascii=False, indent=2)


def detect_language(text: str) -> str:
    if not text:
        return "en"
    chinese_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return "zh" if chinese_count / len(text) > 0.2 else "en"


def call_llm(client: OpenAI, prompt: str, model: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=8192,
    )
    return response.choices[0].message.content


def process_single_item(
    question: str,
    report: str,
    task_id: str,
    reference_map: dict,
    criteria_map: dict,
    client: OpenAI,
    model: str,
    lock: threading.Lock,
    counter: dict,
) -> dict:
    """
    处理单条RACE评分:
    1. 用question匹配reference和criteria
    2. 构建评分prompt (article_1=target, article_2=reference)
    3. 调用LLM judge
    4. 解析JSON -> calculate_weighted_scores -> 归一化
    """
    if not report:
        with lock:
            counter["done"] += 1
        return {"task_id": task_id, "question": question, "error": "Empty report"}

    if question not in reference_map:
        with lock:
            counter["done"] += 1
        return {"task_id": task_id, "question": question, "error": "Reference not found"}

    if question not in criteria_map:
        with lock:
            counter["done"] += 1
        return {"task_id": task_id, "question": question, "error": "Criteria not found"}

    reference_article = reference_map[question]["article"]
    criteria_data = criteria_map[question]
    language = detect_language(question)
    criteria_list_str = format_criteria_list(criteria_data)
    merged_prompt = zh_merged_score_prompt if language == "zh" else en_merged_score_prompt

    user_prompt = merged_prompt.format(
        task_prompt=question,
        article_1=report,
        article_2=reference_article,
        criteria_list=criteria_list_str,
    )

    llm_response_str = None
    llm_output_json = None
    success = False

    for retry in range(MAX_RETRIES):
        try:
            llm_response_str = call_llm(client, user_prompt, model)
            json_str = extract_json_from_markdown(llm_response_str)
            if not json_str:
                raise ValueError("Failed to extract JSON")
            llm_output_json = json.loads(json_str)
            expected_dims = ["comprehensiveness", "insight", "instruction_following", "readability"]
            missing = [d for d in expected_dims if d not in llm_output_json]
            if missing:
                raise ValueError(f"Missing dims: {missing}")
            success = True
            break
        except Exception as e:
            if retry < MAX_RETRIES - 1:
                logger.warning(f"[{task_id}] Retry {retry+1}: {e}")
                time.sleep(min(1.5 ** (retry + 1), 30))
            else:
                logger.error(f"[{task_id}] Failed after {MAX_RETRIES} retries: {e}")

    if not success:
        with lock:
            counter["done"] += 1
        return {"task_id": task_id, "question": question, "error": f"Failed after {MAX_RETRIES} retries"}

    try:
        scores = calculate_weighted_scores(llm_output_json, criteria_data, language)
        target_total = scores["target"]["total"]
        reference_total = scores["reference"]["total"]
        overall_score = target_total / (target_total + reference_total) if (target_total + reference_total) > 0 else 0

        normalized_dims = {}
        for dim in ["comprehensiveness", "insight", "instruction_following", "readability"]:
            dim_key = f"{dim}_weighted_avg"
            t = scores["target"]["dims"].get(dim_key, 0)
            r = scores["reference"]["dims"].get(dim_key, 0)
            normalized_dims[dim] = t / (t + r) if (t + r) > 0 else 0
    except Exception as e:
        with lock:
            counter["done"] += 1
        return {"task_id": task_id, "question": question, "error": f"Score calc: {e}"}

    result = {
        "task_id": task_id,
        "question": question,
        "language": language,
        "comprehensiveness": round(normalized_dims["comprehensiveness"], 4),
        "insight": round(normalized_dims["insight"], 4),
        "instruction_following": round(normalized_dims["instruction_following"], 4),
        "readability": round(normalized_dims["readability"], 4),
        "overall_score": round(overall_score, 4),
        "raw_target_total": round(target_total, 4),
        "raw_reference_total": round(reference_total, 4),
    }

    with lock:
        counter["done"] += 1
        logger.info(f"[{counter['done']}/{counter['total']}] {task_id} overall={overall_score:.4f}")

    return result


def summarize_results(results: list) -> dict:
    successful = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]
    if not successful:
        return {"error": "No successful results", "total": len(results), "failed": len(failed)}

    dims = ["comprehensiveness", "insight", "instruction_following", "readability", "overall_score"]
    summary = {"total": len(results), "successful": len(successful), "failed": len(failed), "averages": {}}
    for dim in dims:
        values = [r[dim] for r in successful]
        summary["averages"][dim] = round(sum(values) / len(values), 4)

    for lang in ["zh", "en"]:
        lang_results = [r for r in successful if r.get("language") == lang]
        if lang_results:
            summary[f"{lang}_count"] = len(lang_results)
            summary[f"{lang}_averages"] = {}
            for dim in dims:
                values = [r[dim] for r in lang_results]
                summary[f"{lang}_averages"][dim] = round(sum(values) / len(values), 4)

    return summary


def main():
    parser = argparse.ArgumentParser(description="Step 3: RACE Evaluation (general-purpose)")
    parser.add_argument("--input", type=str, required=True, help="Input report JSONL file")
    parser.add_argument("--tag", type=str, default="eval", help="Tag for output file naming")
    parser.add_argument("--limit", type=int, default=None, help="Limit items to process")
    parser.add_argument("--workers", type=int, default=5, help="Concurrent workers")
    parser.add_argument("--model", type=str, default=None, help="Override judge model")
    parser.add_argument("--output", type=str, default=None, help="Override output path")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    output_file = args.output or str(OUTPUT_DIR / f"{args.tag}_race_scored.jsonl")
    summary_file = output_file.replace(".jsonl", "_summary.json")

    # API
    api_key = os.getenv("ARK_API_KEY")
    api_base = os.getenv("ARK_API_BASE")
    model = args.model or os.getenv("doubao_16_model_name", "ep-20250724221742-fddgp")
    client = OpenAI(api_key=api_key, base_url=api_base)
    logger.info(f"Judge model: {model}")

    # 加载数据
    report_data = load_jsonl(args.input)
    references = load_jsonl(str(INPUT_DIR / "reference.jsonl"))
    criteria = load_jsonl(str(INPUT_DIR / "criteria.jsonl"))
    logger.info(f"Reports: {len(report_data)}, Refs: {len(references)}, Criteria: {len(criteria)}")

    reference_map = {item["prompt"]: item for item in references}
    criteria_map = {item["prompt"]: item for item in criteria}

    # 断点续跑
    existing_results = []
    existing_ids = set()
    if os.path.exists(output_file):
        existing_results = load_jsonl(output_file)
        existing_ids = {r.get("task_id") for r in existing_results if r.get("task_id")}
        logger.info(f"Found {len(existing_ids)} existing results")

    # 准备待处理数据
    items = []
    for r in report_data:
        task_id = r.get("task_id", "")
        if task_id in existing_ids:
            continue
        question = r.get("question", "")
        report = r.get("report", "")
        if question and report:
            items.append((question, report, task_id))

    if args.limit:
        items = items[:args.limit]

    logger.info(f"Items to evaluate: {len(items)}")

    if not items:
        logger.info("All items already evaluated!")
        if existing_results:
            summary = summarize_results(existing_results)
            print("\n=== RACE Results ===")
            for k, v in summary.get("averages", {}).items():
                print(f"  {k}: {v:.4f}")
        return

    lock = threading.Lock()
    counter = {"done": 0, "total": len(items)}
    new_results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(
                process_single_item,
                q, rep, tid, reference_map, criteria_map, client, model, lock, counter,
            )
            for q, rep, tid in items
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                new_results.append(result)

    all_results = existing_results + new_results
    all_results.sort(key=lambda x: x.get("task_id", ""))
    save_jsonl(all_results, output_file)
    logger.info(f"Saved {len(all_results)} results to {output_file}")

    summary = summarize_results(all_results)
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"=== RACE Evaluation: {args.tag} ===")
    print(f"{'='*50}")
    for k, v in summary.get("averages", {}).items():
        print(f"  {k:30s}: {v:.4f}")
    if "zh_averages" in summary:
        print(f"\n  --- Chinese ({summary.get('zh_count', 0)}) ---")
        for k, v in summary["zh_averages"].items():
            print(f"  {k:30s}: {v:.4f}")
    if "en_averages" in summary:
        print(f"\n  --- English ({summary.get('en_count', 0)}) ---")
        for k, v in summary["en_averages"].items():
            print(f"  {k:30s}: {v:.4f}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
