#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 2: 优化后的Report推理脚本

整体逻辑:
1. 加载DRB数据集（50条）
2. 初始化ReportOrchestrator，使用优化参数 + 自定义prompt覆盖
3. 逐条生成报告：
   - 加载自定义prompt配置(prompts/report_prompts_v2.yaml)
   - 动态替换orchestrator的prompt模板
   - 调用generate_report(question)
   - 保存完整结果（report + trajectory + metadata）
4. 支持断点续跑（检查output文件中已完成的question）
5. 并发控制（每次只跑一条report，因为report本身就包含内部并行）

用法:
  python3 step2_optimize_prompts.py
  python3 step2_optimize_prompts.py --limit 3  # 快速测试3条
  python3 step2_optimize_prompts.py --concurrency 2  # 同时跑2条
"""

import os
import sys
import json
import logging
import threading
import argparse
import time
import yaml
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# 指向 dag-deepresearch 根目录
DAG_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, DAG_ROOT)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ===== API 配置 =====
ARK_API_KEY = "bb6ce7bb-dcd3-4733-9f13-ada2de86ef11"
ARK_API_BASE = "https://ark-cn-beijing.bytedance.net/api/v3"
SERPER_API_KEY = "af31ec29fabd1854a3cc34da3b5324d47ba55168"
JINA_API_KEY = "jina_21ed3799312248a7a1aa73b549bd44f1N3Lm4OdyW66asT108Uu55M83cZh0"
SEED16_MODEL = "ep-20250724221742-fddgp"

# 路径配置
BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "assets" / "input"
OUTPUT_DIR = BASE_DIR / "assets" / "output"
LOG_DIR = BASE_DIR / "assets" / "logs"
PROMPTS_DIR = BASE_DIR / "prompts"


def set_env():
    """设置运行所需的环境变量"""
    os.environ["DEFAULT_MODEL"] = SEED16_MODEL
    os.environ["OPENAI_API_KEY"] = ARK_API_KEY
    os.environ["OPENAI_API_BASE"] = ARK_API_BASE
    os.environ["SERPER_API_KEY"] = SERPER_API_KEY
    os.environ["JINA_API_KEY"] = JINA_API_KEY


def read_jsonl(path):
    """读取JSONL文件"""
    data = []
    if not os.path.exists(path):
        return data
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except Exception:
                    pass
    return data


def write_jsonl_append(path, item, lock):
    """追加写入JSONL"""
    with lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def load_custom_prompts(prompts_path: str) -> dict:
    """加载自定义prompt配置"""
    with open(prompts_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def process_item_report_v2(item: dict, custom_prompts: dict) -> dict:
    """
    使用优化参数和自定义prompt生成Report。

    优化点:
    1. Planning阶段: 强化指令分析，要求提取所有显式和隐式需求，section数量增加到6-10
    2. Research阶段: 更严格的引用要求，多角度搜索，权威来源优先
    3. Synthesis阶段: 学术级写作标准，平滑过渡，交叉引用，数据表格

    架构参数:
    - max_section_steps=30 (从20提高，更深入搜索)
    - summary_interval=8 (从6提高，更多搜索后再总结)
    - section_concurrency=4 (从5降低，减少API限流)
    - max_section_retries=3 (从2提高，更稳健)
    - prompts_type="medical" (使用医学优化prompts)
    """
    from FlashOAgents import OpenAIServerModel
    from FlashOAgents.report_orchestrator import ReportOrchestrator

    agent_model = OpenAIServerModel(
        SEED16_MODEL,
        custom_role_conversions={"tool-call": "assistant", "tool-response": "user"},
        max_completion_tokens=32768,
        api_key=ARK_API_KEY,
        api_base=ARK_API_BASE,
    )

    question = item["question"]
    golden_answer = item.get("answer", "")

    # 构建优化后的topic prompt (DRB专用: 不要求"Final Answer"，只要求写研究报告)
    topic = question

    orchestrator = ReportOrchestrator(
        model=agent_model,
        max_section_steps=30,
        summary_interval=8,
        section_concurrency=4,
        max_section_retries=3,
        prompts_type="medical",
    )

    # 用自定义prompt覆盖默认prompt
    orchestrator.prompts = custom_prompts

    try:
        result = orchestrator.generate_report(topic)
    except Exception as e:
        logger.error(f"Report推理失败 [{item.get('task_id', '')}]: {str(e)[:200]}")
        return None

    report_text = result["report"]
    metadata = result["metadata"]
    outline = result["outline"]

    return {
        "question": question,
        "golden_answer": golden_answer,
        "task_id": item.get("task_id", ""),
        "bench": item.get("bench", ""),
        "metric": item.get("metric", "accuracy"),
        "metadata": item.get("metadata", {}),
        "agent_result": report_text[:500],  # 兼容字段
        "report": report_text,
        "report_outline": outline,
        "report_metadata": metadata,
        "input_tokens": metadata.get("total_input_tokens", 0),
        "output_tokens": metadata.get("total_output_tokens", 0),
        "total_time": metadata.get("elapsed_seconds", 0),
    }


def main():
    parser = argparse.ArgumentParser(description="Step 2: Optimized Report Inference")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items")
    parser.add_argument("--concurrency", type=int, default=1, help="Number of concurrent reports")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    parser.add_argument("--prompts", type=str, default=None, help="Custom prompts YAML path")
    args = parser.parse_args()

    set_env()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    outfile = args.output or str(OUTPUT_DIR / "report_v2_drb_med.jsonl")
    prompts_path = args.prompts or str(PROMPTS_DIR / "report_prompts_v2.yaml")

    # 加载自定义prompt
    logger.info(f"Loading custom prompts from: {prompts_path}")
    custom_prompts = load_custom_prompts(prompts_path)

    # 加载数据
    infile = str(INPUT_DIR / "drb_med_med.jsonl")
    data = read_jsonl(infile)
    logger.info(f"Loaded {len(data)} items from {infile}")

    # 断点续跑
    done_data = read_jsonl(outfile)
    done_qs = set(item.get("question") for item in done_data)
    data_to_run = [item for item in data if item.get("question") not in done_qs]
    logger.info(f"Total={len(data)}, Done={len(done_data)}, To run={len(data_to_run)}")

    if args.limit:
        data_to_run = data_to_run[:args.limit]
        logger.info(f"Limited to {len(data_to_run)} items")

    if not data_to_run:
        logger.info("All items already processed!")
        return

    file_lock = threading.Lock()
    completed = 0
    total = len(data_to_run)

    def process_and_save(item):
        nonlocal completed
        start_t = time.time()
        result = process_item_report_v2(item, custom_prompts)
        elapsed = time.time() - start_t

        if result:
            write_jsonl_append(outfile, result, file_lock)
            with file_lock:
                completed += 1
            report_len = len(result.get("report", ""))
            logger.info(
                f"[{completed}/{total}] {item.get('task_id', '')} done in {elapsed:.1f}s, "
                f"report_len={report_len}, tokens_in={result.get('input_tokens', 0)}, "
                f"tokens_out={result.get('output_tokens', 0)}"
            )
        else:
            with file_lock:
                completed += 1
            logger.error(f"[{completed}/{total}] {item.get('task_id', '')} FAILED after {elapsed:.1f}s")

        return result

    if args.concurrency <= 1:
        # 串行执行
        for item in data_to_run:
            process_and_save(item)
    else:
        # 并发执行
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = [executor.submit(process_and_save, item) for item in data_to_run]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Unexpected error: {e}")

    # 汇总
    all_results = read_jsonl(outfile)
    logger.info(f"\nTotal results: {len(all_results)}")
    if all_results:
        total_tokens = sum(r.get("input_tokens", 0) + r.get("output_tokens", 0) for r in all_results)
        avg_report_len = sum(len(r.get("report", "")) for r in all_results) / len(all_results)
        avg_time = sum(r.get("total_time", 0) for r in all_results) / len(all_results)
        logger.info(f"Avg report length: {avg_report_len:.0f} chars")
        logger.info(f"Avg time per report: {avg_time:.1f}s")
        logger.info(f"Total tokens used: {total_tokens}")


if __name__ == "__main__":
    main()
