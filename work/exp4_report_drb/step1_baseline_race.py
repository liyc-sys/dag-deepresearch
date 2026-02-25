#!/usr/bin/env python3
"""
Step 1: Baseline RACE Evaluation — 用exp3的Report结果跑官方RACE评估

整体逻辑:
1. 加载exp3的report输出(report_drb_med_med.jsonl)，提取question字段作为匹配key，report字段作为target article
2. 加载官方reference.jsonl和criteria.jsonl，通过prompt字段做匹配
3. 对每条问题，构建RACE评分prompt（article_1=我们的report, article_2=reference article）
4. 调用豆包Seed 1.6作为judge，获取4维度逐条评分的JSON
5. 调用calculate_weighted_scores计算加权分
6. 归一化: normalized = target_total / (target_total + reference_total)
7. 输出每条的4维度归一化分 + overall_score，以及汇总统计
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

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 路径配置
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
INPUT_DIR = ASSETS_DIR / "input"
OUTPUT_DIR = ASSETS_DIR / "output" / "scored"
LOG_DIR = ASSETS_DIR / "logs"

# 官方RACE脚本所在目录，用于import评分prompt和工具
DRB_DIR = BASE_DIR.parent / "exp3_med_full" / "official_repos" / "deep_research_bench"

# 数据文件
EXP3_REPORT_FILE = INPUT_DIR / "exp3_report_drb_med_med.jsonl"
REFERENCE_FILE = INPUT_DIR / "reference.jsonl"
CRITERIA_FILE = INPUT_DIR / "criteria.jsonl"

# API配置（必须在导入DRB utils前设置，否则utils/__init__.py中的api.py会报错缺少JINA_API_KEY）
ENV_PATH = Path(__file__).resolve().parents[3] / "0001_utils" / "api" / ".env"
load_dotenv(ENV_PATH)

# 将DRB目录加入sys.path以复用官方工具
sys.path.insert(0, str(DRB_DIR))
from prompt.score_prompt_zh import generate_merged_score_prompt as zh_merged_score_prompt
from prompt.score_prompt_en import generate_merged_score_prompt as en_merged_score_prompt
from utils.score_calculator import calculate_weighted_scores
from utils.json_extractor import extract_json_from_markdown

MAX_RETRIES = 10
MAX_WORKERS = 5


def load_jsonl(path: str) -> list:
    """加载JSONL文件"""
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def save_jsonl(data: list, path: str):
    """保存JSONL文件"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def format_criteria_list(criteria_data: dict) -> str:
    """将criteria格式化为JSON字符串（不含weight信息），用于评分prompt"""
    criteria_for_prompt = {}
    criterions_dict = criteria_data.get("criterions", {})
    for dim, criterions_list in criterions_dict.items():
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
    """简单检测文本语言：如果中文字符占比>20%则认为是中文"""
    if not text:
        return "en"
    chinese_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    ratio = chinese_count / len(text)
    return "zh" if ratio > 0.2 else "en"


def call_llm(client: OpenAI, prompt: str, model: str) -> str:
    """调用LLM获取评分结果"""
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=8192,
    )
    return response.choices[0].message.content


def process_single_item(
    item_data: dict,
    reference_map: dict,
    criteria_map: dict,
    client: OpenAI,
    model: str,
    lock: threading.Lock,
    pbar_info: dict,
) -> dict:
    """
    处理单条数据的RACE评分：
    1. 从exp3结果中取report作为target article
    2. 根据question匹配reference和criteria
    3. 构建评分prompt（中/英文根据问题语言选择）
    4. 调用LLM评分
    5. 解析JSON，计算加权分和归一化分
    """
    question = item_data["question"]
    report = item_data.get("report", "")
    task_id = item_data.get("task_id", "")

    if not report:
        logger.error(f"[{task_id}] report为空，跳过")
        with lock:
            pbar_info["done"] += 1
        return {"task_id": task_id, "question": question, "error": "Empty report"}

    # 匹配reference和criteria（通过question == prompt）
    if question not in reference_map:
        logger.error(f"[{task_id}] 未在reference中找到匹配: {question[:60]}...")
        with lock:
            pbar_info["done"] += 1
        return {"task_id": task_id, "question": question, "error": "Reference not found"}

    if question not in criteria_map:
        logger.error(f"[{task_id}] 未在criteria中找到匹配: {question[:60]}...")
        with lock:
            pbar_info["done"] += 1
        return {"task_id": task_id, "question": question, "error": "Criteria not found"}

    reference_article = reference_map[question]["article"]
    criteria_data = criteria_map[question]

    # 检测语言
    language = detect_language(question)

    # 格式化criteria
    criteria_list_str = format_criteria_list(criteria_data)

    # 选择评分prompt
    merged_prompt = zh_merged_score_prompt if language == "zh" else en_merged_score_prompt

    # 构建评分请求：article_1=我们的report, article_2=reference
    user_prompt = merged_prompt.format(
        task_prompt=question,
        article_1=report,
        article_2=reference_article,
        criteria_list=criteria_list_str,
    )

    # 重试调用LLM
    llm_response_str = None
    llm_output_json = None
    success = False

    for retry in range(MAX_RETRIES):
        try:
            llm_response_str = call_llm(client, user_prompt, model)
            json_str = extract_json_from_markdown(llm_response_str)
            if not json_str:
                raise ValueError("Failed to extract JSON from LLM response")

            llm_output_json = json.loads(json_str)

            expected_dims = ["comprehensiveness", "insight", "instruction_following", "readability"]
            missing = [d for d in expected_dims if d not in llm_output_json]
            if missing:
                raise ValueError(f"Missing dimensions: {missing}")

            success = True
            break

        except Exception as e:
            if retry < MAX_RETRIES - 1:
                logger.warning(f"[{task_id}] Retry {retry + 1}/{MAX_RETRIES}: {e}")
                time.sleep(min(1.5 ** (retry + 1), 30))
            else:
                logger.error(f"[{task_id}] Failed after {MAX_RETRIES} retries: {e}")

    if not success:
        with lock:
            pbar_info["done"] += 1
        return {
            "task_id": task_id,
            "question": question,
            "error": f"Failed after {MAX_RETRIES} retries",
            "model_output_preview": (llm_response_str or "")[:500],
        }

    # 计算加权分
    try:
        scores = calculate_weighted_scores(llm_output_json, criteria_data, language)

        target_total = scores["target"]["total"]
        reference_total = scores["reference"]["total"]
        overall_score = target_total / (target_total + reference_total) if (target_total + reference_total) > 0 else 0

        normalized_dims = {}
        for dim in ["comprehensiveness", "insight", "instruction_following", "readability"]:
            dim_key = f"{dim}_weighted_avg"
            t_score = scores["target"]["dims"].get(dim_key, 0)
            r_score = scores["reference"]["dims"].get(dim_key, 0)
            normalized_dims[dim] = t_score / (t_score + r_score) if (t_score + r_score) > 0 else 0

    except Exception as e:
        logger.error(f"[{task_id}] Score calculation error: {e}")
        with lock:
            pbar_info["done"] += 1
        return {"task_id": task_id, "question": question, "error": f"Score calculation error: {e}"}

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
        pbar_info["done"] += 1
        logger.info(f"[{pbar_info['done']}/{pbar_info['total']}] {task_id} overall={overall_score:.4f} "
                     f"comp={normalized_dims['comprehensiveness']:.4f} "
                     f"ins={normalized_dims['insight']:.4f} "
                     f"if={normalized_dims['instruction_following']:.4f} "
                     f"read={normalized_dims['readability']:.4f}")

    return result


def summarize_results(results: list) -> dict:
    """汇总评估结果"""
    successful = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    if not successful:
        return {"error": "No successful results", "total": len(results), "failed": len(failed)}

    dims = ["comprehensiveness", "insight", "instruction_following", "readability", "overall_score"]
    summary = {
        "total": len(results),
        "successful": len(successful),
        "failed": len(failed),
        "averages": {},
    }

    for dim in dims:
        values = [r[dim] for r in successful]
        summary["averages"][dim] = round(sum(values) / len(values), 4)

    # 按语言分组统计
    for lang in ["zh", "en"]:
        lang_results = [r for r in successful if r.get("language") == lang]
        if lang_results:
            summary[f"{lang}_averages"] = {}
            summary[f"{lang}_count"] = len(lang_results)
            for dim in dims:
                values = [r[dim] for r in lang_results]
                summary[f"{lang}_averages"][dim] = round(sum(values) / len(values), 4)

    return summary


def main():
    parser = argparse.ArgumentParser(description="Step 1: Baseline RACE Evaluation")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items to process")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help="Number of concurrent workers")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    parser.add_argument("--model", type=str, default=None, help="Override judge model name")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    output_file = args.output or str(OUTPUT_DIR / "baseline_race_scored.jsonl")
    summary_file = output_file.replace(".jsonl", "_summary.json")

    # 初始化API客户端
    api_key = os.getenv("ARK_API_KEY")
    api_base = os.getenv("ARK_API_BASE")
    model = args.model or os.getenv("doubao_16_model_name", "ep-20250724221742-fddgp")

    client = OpenAI(api_key=api_key, base_url=api_base)
    logger.info(f"Using judge model: {model}")

    # 加载数据
    logger.info("Loading data...")
    exp3_results = load_jsonl(str(EXP3_REPORT_FILE))
    references = load_jsonl(str(REFERENCE_FILE))
    criteria = load_jsonl(str(CRITERIA_FILE))

    logger.info(f"exp3 results: {len(exp3_results)}, references: {len(references)}, criteria: {len(criteria)}")

    # 构建匹配map（用prompt字段匹配）
    reference_map = {item["prompt"]: item for item in references}
    criteria_map = {item["prompt"]: item for item in criteria}

    # 检查已完成的结果（断点续跑）
    existing_ids = set()
    existing_results = []
    if os.path.exists(output_file):
        existing_results = load_jsonl(output_file)
        existing_ids = {r.get("task_id") for r in existing_results if r.get("task_id")}
        logger.info(f"Found {len(existing_ids)} existing results, will skip them")

    # 过滤待处理项目
    items_to_process = [r for r in exp3_results if r.get("task_id") not in existing_ids]
    if args.limit:
        items_to_process = items_to_process[:args.limit]

    logger.info(f"Items to process: {len(items_to_process)}")

    if not items_to_process:
        logger.info("All items already processed!")
        if existing_results:
            summary = summarize_results(existing_results)
            print("\n=== Baseline RACE Results ===")
            for k, v in summary.get("averages", {}).items():
                print(f"  {k}: {v:.4f}")
        return

    # 并发处理
    lock = threading.Lock()
    pbar_info = {"done": 0, "total": len(items_to_process)}
    new_results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(
                process_single_item,
                item, reference_map, criteria_map, client, model, lock, pbar_info,
            )
            for item in items_to_process
        ]

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                new_results.append(result)

    # 合并结果
    all_results = existing_results + new_results
    all_results.sort(key=lambda x: x.get("task_id", ""))

    # 保存
    save_jsonl(all_results, output_file)
    logger.info(f"Saved {len(all_results)} results to {output_file}")

    # 汇总
    summary = summarize_results(all_results)
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info(f"Summary saved to {summary_file}")

    # 打印结果
    print("\n" + "=" * 50)
    print("=== Baseline RACE Evaluation Results ===")
    print("=" * 50)
    for k, v in summary.get("averages", {}).items():
        print(f"  {k:30s}: {v:.4f}")

    if "zh_averages" in summary:
        print(f"\n  --- Chinese ({summary.get('zh_count', 0)} items) ---")
        for k, v in summary["zh_averages"].items():
            print(f"  {k:30s}: {v:.4f}")

    if "en_averages" in summary:
        print(f"\n  --- English ({summary.get('en_count', 0)} items) ---")
        for k, v in summary["en_averages"].items():
            print(f"  {k:30s}: {v:.4f}")

    print("=" * 50)


if __name__ == "__main__":
    main()
