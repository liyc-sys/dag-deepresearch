#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step2_run_eval.py
使用多种推理框架对8个医学 benchmark 进行推理评测。

支持的框架：
- flashsearcher：SearchAgent，无 planning step（patch 掉规划）
- dag：SearchAgent，含 planning step（使用 default prompts）
- dag_med：SearchAgent，含 planning step（使用 medical prompts）
- report：ReportOrchestrator（两层DAG，生成结构化报告并提取答案）

整体逻辑：
- 模型固定为 seed16（ARK API）
- 并发=8，max_steps=40（report模式除外）
- 断点续跑（基于 question 字段去重）
- 输出：assets/output/{framework}_{bench_key}_med.jsonl

用法：
  python3 step2_run_eval.py --framework flashsearcher --datasets bc_en_med
  python3 step2_run_eval.py --framework report --datasets bc_zh_med --concurrency 2
  python3 step2_run_eval.py --framework dag_med  # 跑全部8个benchmark
"""
import os
import sys
import json
import logging
import threading
import argparse
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# 指向 dag-deepresearch 根目录
DAG_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, DAG_ROOT)

# ===== API 配置 =====
ARK_API_KEY    = "bb6ce7bb-dcd3-4733-9f13-ada2de86ef11"
ARK_API_BASE   = "https://ark-cn-beijing.bytedance.net/api/v3"
GPT_API_KEY    = "f5CBx539CnpxCx0ylnAshe3mjJpd71Uk_GPT_AK"
GPT_API_BASE   = "https://search.bytedance.net/gpt/openapi/online/v2/crawl"
SERPER_API_KEY = "af31ec29fabd1854a3cc34da3b5324d47ba55168"
JINA_API_KEY   = "jina_21ed3799312248a7a1aa73b549bd44f1N3Lm4OdyW66asT108Uu55M83cZh0"

# 固定使用 seed16 模型
SEED16_MODEL   = "ep-20250724221742-fddgp"

# ===== 数据集配置 =====
BENCHMARKS = {
    "bc_en_med": {"desc": "BrowseComp Medical EN",         "metric": "accuracy", "file": "bc_en_med_med.jsonl"},
    "bc_zh_med": {"desc": "BrowseComp Medical ZH",         "metric": "accuracy", "file": "bc_zh_med_med.jsonl"},
    "dsq_med":   {"desc": "DeepSearchQA Medical",          "metric": "f1",       "file": "dsq_med_med.jsonl"},
    "drb_med":   {"desc": "DRB Medical",                   "metric": "accuracy", "file": "drb_med_med.jsonl"},
    "gaia_med":  {"desc": "GAIA Medical",                  "metric": "accuracy", "file": "gaia_med_med.jsonl"},
    "hle_med":   {"desc": "HLE Medical",                   "metric": "accuracy", "file": "hle_med_med.jsonl"},
    "drb2_med":  {"desc": "DeepResearch-Bench-II Medical", "metric": "rubric",   "file": "drb2_med_med.jsonl"},
    "xbench_med":{"desc": "XBench Medical",                "metric": "accuracy", "file": "xbench_med_med.jsonl"},
    "researchqa_med":      {"desc": "ResearchQA Medical",           "metric": "accuracy", "file": "researchqa_med_med.jsonl"},
    "researchqa_med_test10": {"desc": "ResearchQA Medical Test10", "metric": "accuracy", "file": "researchqa_med_test10.jsonl"},
}

EXP_DIR    = os.path.dirname(__file__)
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


def set_env():
    """设置 seed16 运行所需的环境变量"""
    os.environ["DEFAULT_MODEL"]   = SEED16_MODEL
    os.environ["OPENAI_API_KEY"]  = ARK_API_KEY
    os.environ["OPENAI_API_BASE"] = ARK_API_BASE
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


def write_jsonl_append(path, item, lock):
    with lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def build_model():
    """构建 ARK API 模型（seed16）"""
    from FlashOAgents import OpenAIServerModel
    return OpenAIServerModel(
        SEED16_MODEL,
        custom_role_conversions={"tool-call": "assistant", "tool-response": "user"},
        max_completion_tokens=32768,
        api_key=ARK_API_KEY,
        api_base=ARK_API_BASE,
    )


def process_item_dag(item, summary_interval=8, max_steps=40, prompts_type="default"):
    """
    DAG 模式：使用 SearchAgent（含 planning step）推理一条数据。
    与 exp2 的 process_item 逻辑一致，仅固定 seed16 模型。
    prompts_type 支持 "default"（原始）和 "medical"（医学优化版，含具体搜索词指引）。
    """
    from FlashOAgents import OpenAIServerModel
    from base_agent import SearchAgent

    agent_model = OpenAIServerModel(
        SEED16_MODEL,
        custom_role_conversions={"tool-call": "assistant", "tool-response": "user"},
        max_completion_tokens=32768,
        api_key=ARK_API_KEY,
        api_base=ARK_API_BASE,
    )
    search_agent = SearchAgent(
        agent_model,
        summary_interval=summary_interval,
        prompts_type=prompts_type,
        max_steps=max_steps
    )

    question = item["question"]
    golden_answer = item["answer"]

    try:
        result = search_agent(question)
    except Exception as e:
        logger.error(f"DAG推理失败: {str(e)[:100]}")
        return None

    return {
        "question":      question,
        "golden_answer": golden_answer,
        "task_id":       item.get("task_id", ""),
        "bench":         item.get("bench", ""),
        "metric":        item.get("metric", "accuracy"),
        "metadata":      item.get("metadata", {}),
        **result,
    }


def process_item_flashsearcher(item, summary_interval=8, max_steps=40):
    """
    FlashSearcher 模式：使用 SearchAgent，但 patch 掉 planning_step，不执行规划。
    planning_step 被替换为仅记录一个空 PlanningStep，不调用 LLM，从而节省 token 并跳过规划。
    """
    from FlashOAgents import OpenAIServerModel
    from FlashOAgents.memory import PlanningStep
    import time
    from base_agent import SearchAgent

    agent_model = OpenAIServerModel(
        SEED16_MODEL,
        custom_role_conversions={"tool-call": "assistant", "tool-response": "user"},
        max_completion_tokens=32768,
        api_key=ARK_API_KEY,
        api_base=ARK_API_BASE,
    )
    search_agent = SearchAgent(
        agent_model,
        summary_interval=summary_interval,
        prompts_type="default",
        max_steps=max_steps
    )

    # Patch: 跳过 planning step，不调用 LLM
    def skip_planning(task):
        step = PlanningStep(
            model_input_messages=[],
            plan="[No Planning - FlashSearcher Mode]",
            plan_think="",
            plan_reasoning="",
            start_time=time.time(),
            end_time=time.time(),
            duration=0.0,
            input_tokens=0,
            output_tokens=0,
        )
        search_agent.agent_fn.memory.steps.append(step)
        return step

    search_agent.agent_fn.planning_step = skip_planning

    question = item["question"]
    golden_answer = item["answer"]

    try:
        result = search_agent(question)
    except Exception as e:
        logger.error(f"FlashSearcher推理失败: {str(e)[:100]}")
        return None

    return {
        "question":      question,
        "golden_answer": golden_answer,
        "task_id":       item.get("task_id", ""),
        "bench":         item.get("bench", ""),
        "metric":        item.get("metric", "accuracy"),
        "metadata":      item.get("metadata", {}),
        **result,
    }


def process_item_report(item, depth="ultra-lite", summary_interval=6):
    """
    Report 模式：使用 ReportOrchestrator（两层DAG）生成研究报告，并从报告中提取最终答案。

    核心思路：
    1. 将问题转化为一个研究报告主题
    2. 使用 ReportOrchestrator 生成结构化报告（Layer 1: 大纲, Layer 2: 各section调用SearchAgent）
    3. 从报告末尾提取 "Final Answer" 或 "最终答案" 部分作为agent_result

    深度模式：
    - "full"（完整版，适合rubric评分）：max_section_steps=10, section_concurrency=3, 详细报告, 预计25-30分钟/题
    - "lite"（精简版）：max_section_steps=5, section_concurrency=5, 简洁报告, 预计10-15分钟/题
    - "ultra-lite"（超精简，适合accuracy/F1）：max_section_steps=3, section_concurrency=8, 核心要点, 预计5-8分钟/题
    """
    from FlashOAgents import OpenAIServerModel
    from FlashOAgents.report_orchestrator import ReportOrchestrator
    import re

    agent_model = OpenAIServerModel(
        SEED16_MODEL,
        custom_role_conversions={"tool-call": "assistant", "tool-response": "user"},
        max_completion_tokens=32768,
        api_key=ARK_API_KEY,
        api_base=ARK_API_BASE,
    )

    question = item["question"]
    golden_answer = item["answer"]

    # 根据深度模式调整参数
    if depth == "full":
        max_section_steps = 10
        section_concurrency = 3
        # 完整版：详细的研究报告提示
        topic = f"""Research Question: {question}

Please write a comprehensive research report that:
1. Analyzes this question from multiple perspectives
2. Gathers and evaluates relevant information through web search
3. Presents clear reasoning and evidence
4. Provides thorough verification of findings
5. Concludes with a definitive answer

IMPORTANT: Your report MUST end with a clearly marked "## Final Answer" section that contains your answer to the question. Format:

## Final Answer
[Your answer here]
"""
    elif depth == "lite":
        max_section_steps = 5
        section_concurrency = 5
        # 精简版：聚焦核心要素的简洁提示
        topic = f"""Research Question: {question}

Please write a focused research report with 4-5 sections that:
1. Identifies key information needed to answer the question
2. Gathers evidence through targeted web search
3. Provides clear reasoning
4. Concludes with a definitive answer

Keep the report concise and focused. IMPORTANT: Your report MUST end with a clearly marked "## Final Answer" section. Format:

## Final Answer
[Your answer here]
"""
    else:  # ultra-lite
        max_section_steps = 3
        section_concurrency = 8
        # 超精简版：快速核心要点
        topic = f"""Research Question: {question}

Please write a concise research report with 3-4 sections maximum that:
1. Identifies the most critical information needed
2. Gathers key evidence through targeted search
3. Provides direct reasoning
4. Gives a clear, definitive answer

Keep each section brief and focused on essential points only. IMPORTANT: Your report MUST end with a clearly marked "## Final Answer" section. Format:

## Final Answer
[Your answer here]
"""

    orchestrator = ReportOrchestrator(
        model=agent_model,
        max_section_steps=max_section_steps,
        summary_interval=summary_interval,
        section_concurrency=section_concurrency,
        max_section_retries=2,
        prompts_type="default",
    )

    try:
        result = orchestrator.generate_report(topic)
    except Exception as e:
        logger.error(f"Report推理失败: {str(e)[:200]}")
        return None

    # 从报告中提取最终答案
    report_text = result["report"]
    agent_result = ""

    # 尝试匹配 "## Final Answer" 或 "## 最终答案" 等标记
    patterns = [
        r"##\s*Final Answer[:\s]*\n(.+?)(?=\n##|$)",
        r"##\s*最终答案[:\s]*\n(.+?)(?=\n##|$)",
        r"##\s*Conclusion[:\s]*\n(.+?)(?=\n##|$)",
        r"##\s*结论[:\s]*\n(.+?)(?=\n##|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, report_text, re.DOTALL | re.IGNORECASE)
        if match:
            agent_result = match.group(1).strip()
            break

    # 如果没找到标记，取报告最后500字符
    if not agent_result:
        agent_result = report_text[-500:].strip()
        logger.warning(f"未找到明确的Final Answer标记，使用报告末尾内容")

    # 计算总token和时间
    metadata = result["metadata"]
    outline = result["outline"]

    return {
        "question":      question,
        "golden_answer": golden_answer,
        "task_id":       item.get("task_id", ""),
        "bench":         item.get("bench", ""),
        "metric":        item.get("metric", "accuracy"),
        "metadata":      item.get("metadata", {}),
        "agent_result":  agent_result,
        "report":        report_text,
        "report_outline": outline,
        "report_metadata": metadata,
        "input_tokens":  metadata.get("total_input_tokens", 0),
        "output_tokens": metadata.get("total_output_tokens", 0),
        "total_time":    metadata.get("elapsed_seconds", 0),
    }


def run_eval(framework, dataset_key, concurrency=8, max_steps=40, summary_interval=8):
    """对一个 (framework, dataset) 组合运行评测"""
    ds_cfg  = BENCHMARKS[dataset_key]
    infile  = os.path.join(INPUT_DIR, ds_cfg["file"])
    outfile = os.path.join(OUTPUT_DIR, f"{framework}_{dataset_key}_med.jsonl")

    logger.info(f"\n{'='*50}")
    logger.info(f"[{framework}] × [{dataset_key}] 开始评测")
    logger.info(f"  输入: {infile}")
    logger.info(f"  输出: {outfile}")

    data = read_jsonl(infile)
    if not data:
        logger.error(f"数据文件不存在或为空: {infile}")
        return

    # 断点续跑（基于 question 去重）
    done_data     = read_jsonl(outfile)
    done_qs       = set(item.get("question") for item in done_data)
    data_to_run   = [item for item in data if item.get("question") not in done_qs]
    logger.info(f"  总条数={len(data)}, 已完成={len(done_data)}, 待运行={len(data_to_run)}")

    if not data_to_run:
        logger.info("  [跳过] 已全部完成")
        return

    file_lock = threading.Lock()
    if framework == "flashsearcher":
        process_fn = lambda item, si, ms: process_item_flashsearcher(item, si, ms)
    elif framework == "dag_med":
        process_fn = lambda item, si, ms: process_item_dag(item, si, ms, prompts_type="medical")
    elif framework == "report":
        # Report模式：根据 metric 类型和数据集自动选择深度
        # - researchqa: 深度研究任务，使用 full 模式
        # - rubric评分: 使用 full 模式
        # - 其他: 使用 ultra-lite 模式
        metric = ds_cfg.get("metric", "accuracy")
        if "researchqa" in dataset_key.lower():
            depth = "full"
            logger.info(f"  Report深度模式: {depth} (ResearchQA深度研究任务)")
        elif metric == "rubric":
            depth = "full"
            logger.info(f"  Report深度模式: {depth} (metric={metric})")
        else:
            depth = "ultra-lite"
            logger.info(f"  Report深度模式: {depth} (metric={metric})")
        process_fn = lambda item, si, ms: process_item_report(
            item,
            depth=depth,
            summary_interval=si
        )
    else:  # dag
        process_fn = lambda item, si, ms: process_item_dag(item, si, ms, prompts_type="default")

    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(process_fn, item, summary_interval, max_steps)
            for item in data_to_run
        ]
        for future in tqdm(as_completed(futures), total=len(futures),
                           desc=f"{framework}×{dataset_key}"):
            result = future.result()
            if result:
                results.append(result)
                write_jsonl_append(outfile, result, file_lock)

    logger.info(f"  完成: 新增={len(results)}, 总计={len(done_data)+len(results)}")


def main():
    parser = argparse.ArgumentParser(description="exp3_med_full 推理评测脚本")
    parser.add_argument("--framework", choices=["flashsearcher", "dag", "dag_med", "report"], required=True,
                        help="推理框架：dag_med=使用医学优化版prompts, report=使用两层DAG报告生成（自动选择深度）")
    parser.add_argument("--datasets",  nargs="+", default=list(BENCHMARKS.keys()),
                        help=f"要评测的数据集: {list(BENCHMARKS.keys())}")
    parser.add_argument("--concurrency",      type=int, default=8,  help="并发数")
    parser.add_argument("--max_steps",        type=int, default=40, help="每条最大推理步数")
    parser.add_argument("--summary_interval", type=int, default=8,  help="摘要间隔")
    args = parser.parse_args()

    set_env()
    logger.info(f"框架: {args.framework}")
    logger.info(f"模型: {SEED16_MODEL}")
    logger.info(f"数据集: {args.datasets}")
    logger.info(f"并发数: {args.concurrency}, 最大步数: {args.max_steps}")

    for dataset_key in args.datasets:
        if dataset_key not in BENCHMARKS:
            logger.warning(f"未知数据集: {dataset_key}")
            continue
        run_eval(
            args.framework, dataset_key,
            concurrency=args.concurrency,
            max_steps=args.max_steps,
            summary_interval=args.summary_interval
        )

    logger.info("\n[完成] 所有评测任务结束")


if __name__ == "__main__":
    main()
