#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step2_run_eval.py
使用dag-deepresearch (FlashSearcher)对三个benchmark×两个模型进行推理评测。

整体逻辑：
1. 为每个(model, dataset)组合设置环境变量
2. 调用FlashSearcher做多步搜索推理
3. 断点续跑：已完成的question直接跳过
4. 结果保存到 assets/output/{model}_{dataset}.jsonl
"""
import os
import sys
import json
import logging
import threading
import argparse
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# 指向dag-deepresearch根目录
DAG_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, DAG_ROOT)

# ===== API 配置 =====
ARK_API_KEY  = "bb6ce7bb-dcd3-4733-9f13-ada2de86ef11"
ARK_API_BASE = "https://ark-cn-beijing.bytedance.net/api/v3"
GPT_API_KEY  = "f5CBx539CnpxCx0ylnAshe3mjJpd71Uk_GPT_AK"
GPT_API_BASE = "https://search.bytedance.net/gpt/openapi/online/v2/crawl"
SERPER_API_KEY = "af31ec29fabd1854a3cc34da3b5324d47ba55168"
JINA_API_KEY   = "jina_21ed3799312248a7a1aa73b549bd44f1N3Lm4OdyW66asT108Uu55M83cZh0"

# ===== 模型配置 =====
MODELS = {
    "seed16":   {"model": "ep-20250724221742-fddgp", "api_key": ARK_API_KEY, "api_base": ARK_API_BASE},
    "seed18":   {"model": "ep-20260116160300-kq8ft", "api_key": ARK_API_KEY, "api_base": ARK_API_BASE},
    "gpt41":    {"model": "gpt-4.1-2025-04-14",     "api_key": GPT_API_KEY,  "api_base": GPT_API_BASE},
}

# ===== 数据集配置 =====
DATASETS = {
    # 通用benchmark（原始bc_en_50/bc_zh/dsq）
    "bc_en":      {"desc": "BrowseComp EN",           "metric": "accuracy", "file": "bc_en_50.jsonl"},
    "bc_zh":      {"desc": "BrowseComp ZH",           "metric": "accuracy", "file": "bc_zh_50.jsonl"},
    "dsq":        {"desc": "DeepSearchQA",             "metric": "f1",       "file": "dsq_50.jsonl"},
    # 医学子集benchmark
    "bc_en_med":  {"desc": "BrowseComp Medical",      "metric": "accuracy", "file": "bc_en_med_30.jsonl"},
    "dsq_med":    {"desc": "DeepSearchQA Medical",    "metric": "f1",       "file": "dsq_med_30.jsonl"},
    "hle_med":    {"desc": "HLE Biology/Medicine",    "metric": "accuracy", "file": "hle_med_30.jsonl"},
}

EXP_DIR = os.path.dirname(__file__)
INPUT_DIR  = os.path.join(EXP_DIR, "assets/input")
OUTPUT_DIR = os.path.join(EXP_DIR, "assets/output")
LOG_DIR    = os.path.join(EXP_DIR, "assets/logs")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def set_env(model_key):
    """设置运行所需的环境变量"""
    cfg = MODELS[model_key]
    os.environ["DEFAULT_MODEL"]   = cfg["model"]
    os.environ["OPENAI_API_KEY"]  = cfg["api_key"]
    os.environ["OPENAI_API_BASE"] = cfg["api_base"]
    os.environ["SERPER_API_KEY"]  = SERPER_API_KEY
    os.environ["JINA_API_KEY"]    = JINA_API_KEY


def read_jsonl(path):
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


def write_jsonl_append(path, item):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def process_item(item, model, summary_interval, max_steps):
    """调用SearchAgent推理一条数据"""
    from FlashOAgents import OpenAIServerModel
    from base_agent import SearchAgent

    api_base = os.environ.get("OPENAI_API_BASE", "")
    api_key  = os.environ.get("OPENAI_API_KEY")

    # GPT代理需要AzureOpenAI客户端（标准OpenAI客户端会404）
    if "search.bytedance.net" in api_base:
        from openai import AzureOpenAI
        from FlashOAgents.models import OpenAIServerModel as _BaseModel

        class AzureOpenAIServerModel(_BaseModel):
            def __init__(self, model_id, api_base, api_key, **kwargs):
                super().__init__(model_id, **kwargs)
                self.client = AzureOpenAI(
                    azure_endpoint=api_base,
                    api_version="2024-03-01-preview",
                    api_key=api_key,
                )

        agent_model = AzureOpenAIServerModel(
            model,
            api_base=api_base,
            api_key=api_key,
            custom_role_conversions={"tool-call": "assistant", "tool-response": "user"},
            max_completion_tokens=32768,
        )
    else:
        agent_model = OpenAIServerModel(
            model,
            custom_role_conversions={"tool-call": "assistant", "tool-response": "user"},
            max_completion_tokens=32768,
            api_key=api_key,
            api_base=api_base,
        )
    search_agent = SearchAgent(
        agent_model,
        summary_interval=summary_interval,
        prompts_type="default",
        max_steps=max_steps
    )

    question = item["question"]
    golden_answer = item["answer"]

    try:
        result = search_agent(question)
    except Exception as e:
        logger.error(f"推理失败: {str(e)[:100]}")
        return None

    return {
        "question": question,
        "golden_answer": golden_answer,
        "task_id": item.get("task_id", ""),
        "metadata": item.get("metadata", {}),
        **result,
    }


def run_eval(model_key, dataset_key, concurrency=8, max_steps=40, summary_interval=8):
    """对一个(model, dataset)组合运行评测"""
    set_env(model_key)
    model_cfg  = MODELS[model_key]
    model_name = model_cfg["model"]
    ds_cfg     = DATASETS[dataset_key]

    infile  = os.path.join(INPUT_DIR, ds_cfg["file"])
    outfile = os.path.join(OUTPUT_DIR, f"{model_key}_{dataset_key}.jsonl")

    logger.info(f"\n{'='*50}")
    logger.info(f"[{model_key}] × [{dataset_key}] 开始评测")
    logger.info(f"  模型: {model_name}")
    logger.info(f"  输入: {infile}")
    logger.info(f"  输出: {outfile}")

    data = read_jsonl(infile)
    if not data:
        logger.error(f"数据文件不存在或为空: {infile}")
        return

    # 断点续跑
    done_data = read_jsonl(outfile)
    done_questions = set(item.get("question") for item in done_data)
    data_to_run = [item for item in data if item.get("question") not in done_questions]
    logger.info(f"  总条数={len(data)}, 已完成={len(done_data)}, 待运行={len(data_to_run)}")

    if not data_to_run:
        logger.info(f"  [跳过] 已全部完成")
        return

    file_lock = threading.Lock()

    def safe_write(result):
        with file_lock:
            write_jsonl_append(outfile, result)

    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(process_item, item, model_name, summary_interval, max_steps)
            for item in data_to_run
        ]
        for future in tqdm(as_completed(futures), total=len(futures),
                           desc=f"{model_key}×{dataset_key}"):
            result = future.result()
            if result:
                results.append(result)
                safe_write(result)

    logger.info(f"  完成: 新增={len(results)}, 总计={len(done_data)+len(results)}")


def main():
    parser = argparse.ArgumentParser(description="dag-deepresearch 评测脚本")
    parser.add_argument("--models",    nargs="+", default=list(MODELS.keys()),
                        help=f"要评测的模型: {list(MODELS.keys())}")
    parser.add_argument("--datasets",  nargs="+", default=list(DATASETS.keys()),
                        help=f"要评测的数据集: {list(DATASETS.keys())}")
    parser.add_argument("--concurrency", type=int, default=8,  help="并发数")
    parser.add_argument("--max_steps",   type=int, default=40, help="每条最大推理步数")
    parser.add_argument("--summary_interval", type=int, default=8, help="摘要间隔")
    args = parser.parse_args()

    logger.info(f"评测模型: {args.models}")
    logger.info(f"评测数据集: {args.datasets}")
    logger.info(f"并发数: {args.concurrency}, 最大步数: {args.max_steps}")

    for model_key in args.models:
        for dataset_key in args.datasets:
            run_eval(
                model_key, dataset_key,
                concurrency=args.concurrency,
                max_steps=args.max_steps,
                summary_interval=args.summary_interval
            )

    logger.info("\n[完成] 所有评测任务结束")


if __name__ == "__main__":
    main()
