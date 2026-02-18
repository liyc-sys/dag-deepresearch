#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step4_score.py
对 flashsearcher、dag、swalm 三个框架的推理结果进行统一 LLM-Judge 评分。

整体逻辑：
1. 读取 assets/output/{framework}_{bench_key}_med.jsonl
2. 按 benchmark 类型选择评分策略：
   - dsq_med → F1（DSQ judge：计算 precision/recall/f1）
   - 其余7个 → accuracy（BrowseComp judge：二分类 is_correct）
3. 使用 GPT-4.1（AzureOpenAI 字节内部代理）作为 Judge，与 SWALM 实验保持一致
4. 断点续跑（已评分条目通过 question 字段跳过）
5. 输出：
   - assets/output/scored/{framework}_{bench_key}_scored.jsonl
   - assets/output/scored/{framework}_{bench_key}_summary.json
   - assets/output/scored/all_summaries.json

用法：
  python3 step4_score.py                         # 评分所有框架×benchmark
  python3 step4_score.py --frameworks swalm      # 只评 swalm
  python3 step4_score.py --benches bc_en_med hle_med  # 只评指定 benchmark
"""
import os
import sys
import json
import re
import argparse
import logging
from openai import AzureOpenAI
from tqdm import tqdm

EXP_DIR    = os.path.dirname(__file__)
OUTPUT_DIR = os.path.join(EXP_DIR, "assets/output")
SCORED_DIR = os.path.join(EXP_DIR, "assets/output/scored")
os.makedirs(SCORED_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ===== Judge LLM (GPT-4.1 via 字节内部代理) =====
GPT_API_KEY  = "f5CBx539CnpxCx0ylnAshe3mjJpd71Uk_GPT_AK"
GPT_API_BASE = "https://search.bytedance.net/gpt/openapi/online/v2/crawl"
GPT_MODEL    = "gpt-4.1-2025-04-14"

judge_client = AzureOpenAI(
    api_key=GPT_API_KEY,
    azure_endpoint=GPT_API_BASE,
    api_version="2024-02-01"
)

FRAMEWORKS = ["flashsearcher", "dag", "swalm", "dag_med"]

BENCHMARKS = {
    "bc_en_med": "accuracy",
    "bc_zh_med": "accuracy",
    "dsq_med":   "f1",
    "drb_med":   "accuracy",
    "gaia_med":  "accuracy",
    "hle_med":   "accuracy",
    "drb2_med":  "rubric",   # DeepResearch-Bench-II rubric-based eval
    "xbench_med":"accuracy",
}

# ===== BrowseComp Judge Prompt =====
BC_JUDGE_PROMPT = """\
You are an expert judge evaluating whether a model's response correctly answers a question.

## Question
{question}

## Ground Truth Answer
{correct_answer}

## Model's Response
{response}

## Task
Determine if the model's response contains the correct answer. The answer may be expressed differently but should be semantically equivalent to the ground truth.

Consider:
1. For numerical answers: allow small rounding differences
2. For names/entities: allow minor spelling variations or different formats
3. For factual answers: the core information must match

Output ONLY a JSON object:
```json
{{
    "extracted_answer": "<the answer extracted from the model's response, or 'NO_ANSWER' if none found>",
    "reasoning": "<brief explanation>",
    "is_correct": <true or false>
}}
```""".strip()

# ===== DeepSearchQA Judge Prompt =====
DSQ_JUDGE_PROMPT = """\
Your task is to evaluate whether a given "AI Response" for a specific "User Prompt" arrived at the correct answer.

**Answer Correctness Task**
- Identify the "Prompt Type": "{prompt_type}".
- Refer to the "Correct Answer": "{answer}".
- For 'Single Answer': Check if the response provides the correct answer (semantically).
- For 'Set Answer': Check if the response includes each item from the provided ground truth.

**Output Format** (JSON only):
```json
{{
  "Answer Correctness": {{
    "Explanation": "...",
    "Correctness Details": {{"<each_expected_answer>": true_or_false}},
    "Excessive Answers": []
  }}
}}
```

User Prompt: {prompt}
Correct Answer: {answer}
AI Response: {response}
Rating:""".strip()


def call_judge(prompt, max_retries=3):
    """调用 GPT-4.1 作为 judge"""
    for attempt in range(max_retries):
        try:
            resp = judge_client.chat.completions.create(
                model=GPT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=1024,
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.warning(f"Judge调用失败(attempt {attempt+1}): {e}")
    return None


def parse_json_from_text(text):
    """从文本中提取 JSON"""
    if not text:
        return None
    text = re.sub(r'```(?:json)?\s*', '', text).strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return None


def judge_browsecomp(item):
    """BrowseComp 评分：LLM judge 返回 is_correct"""
    question = item.get("question", "")
    golden   = item.get("golden_answer", "")
    response = item.get("agent_result", "")

    if not response:
        return False, {"error": "no agent_result"}

    prompt = BC_JUDGE_PROMPT.format(
        question=question,
        correct_answer=golden,
        response=str(response)[:3000]
    )
    raw    = call_judge(prompt)
    parsed = parse_json_from_text(raw)
    if parsed:
        is_correct = bool(parsed.get("is_correct", False))
        return is_correct, parsed
    return False, {"raw": raw, "error": "parse_failed"}


def judge_deepsearchqa(item):
    """DeepSearchQA 评分：计算 P/R/F1"""
    question    = item.get("question", "")
    golden      = item.get("golden_answer", "")
    response    = item.get("agent_result", "")
    metadata    = item.get("metadata", {})
    prompt_type = metadata.get("answer_type", "Single Answer")

    if not response:
        return 0.0, 0.0, 0.0, {"error": "no agent_result"}

    prompt = DSQ_JUDGE_PROMPT.format(
        prompt_type=prompt_type,
        prompt=question,
        answer=golden,
        response=str(response)[:3000]
    )
    raw    = call_judge(prompt)
    parsed = parse_json_from_text(raw)

    try:
        ac        = parsed["Answer Correctness"]
        details   = ac.get("Correctness Details", {})
        excessive = ac.get("Excessive Answers", [])

        correct_count    = sum(1 for v in details.values() if v)
        total_expected   = len(details)
        total_predicted  = correct_count + len(excessive)

        precision = correct_count / total_predicted if total_predicted > 0 else 0.0
        recall    = correct_count / total_expected  if total_expected > 0 else 0.0
        f1        = (2 * precision * recall / (precision + recall)
                     if precision + recall > 0 else 0.0)
        return precision, recall, f1, parsed
    except Exception as e:
        return 0.0, 0.0, 0.0, {"raw": raw, "error": str(e)}


# ===== DRB2 Rubric Judge Prompt =====
DRB2_JUDGE_PROMPT = """\
You will receive a research report/response, a task description, and a list of rubric items. Your job is to assess whether the response satisfies each rubric item.

Scoring rule per rubric item:
- Score = 1: The response clearly satisfies the rubric item (specific factual/analytical/structural requirement is met).
- Score = 0: The response does NOT mention this rubric item at all, or it's unclear.
- Score = -1: The response explicitly contradicts or incorrectly addresses this rubric item.

For EACH rubric item, output JSON with:
1. "rubric_item": exact copy of the rubric item text
2. "score": 1, 0, or -1
3. "reason": brief explanation (1-2 sentences)

Output format (JSON array only, no extra text):
[
  {{"rubric_item": "...", "score": 1, "reason": "..."}},
  ...
]

Task: {task}

Rubric items to evaluate:
{rubric_items_json}

Response to evaluate:
{response}""".strip()


def judge_drb2_rubric(item, chunk_size=40):
    """
    DRB2 Rubric 评分：对每个 rubric 条目（info_recall/analysis/presentation）进行 1/0/-1 评分。

    整体逻辑：
    1. 从 item["metadata"]["rubric"] 读取三个维度的 rubric 条目
    2. 将所有条目合并（或按 chunk_size 分批）发给 GPT-4.1 judge
    3. 每条 rubric 得到 1/0/-1 分数
    4. 计算：pass_rate = count(score==1) / total_items
    5. 返回 (pass_rate, detail_dict) 用于 score_file 汇总
    """
    question = item.get("question", "")
    metadata = item.get("metadata", {})
    rubric   = metadata.get("rubric", {})
    response = item.get("agent_result", "")

    if not response:
        return 0.0, {"error": "no agent_result"}
    if not rubric:
        return 0.0, {"error": "no rubric in metadata"}

    # 合并所有维度的 rubric 条目
    all_items = []
    for dim in ["info_recall", "analysis", "presentation"]:
        for r_item in rubric.get(dim, []):
            all_items.append({"dimension": dim, "text": r_item})

    if not all_items:
        return 0.0, {"error": "empty rubric items"}

    # 按 chunk_size 批次处理
    all_scores = []
    response_truncated = str(response)[:6000]  # 截断过长的 response

    for i in range(0, len(all_items), chunk_size):
        chunk = all_items[i:i + chunk_size]
        rubric_texts = [r["text"] for r in chunk]

        prompt = DRB2_JUDGE_PROMPT.format(
            task=question[:500],
            rubric_items_json=json.dumps(rubric_texts, ensure_ascii=False, indent=2),
            response=response_truncated,
        )
        raw    = call_judge(prompt, max_retries=3)
        # 解析 JSON 数组
        scored_chunk = None
        if raw:
            raw_clean = re.sub(r'```(?:json)?\s*', '', raw).strip().rstrip('`')
            try:
                scored_chunk = json.loads(raw_clean)
            except Exception:
                # 尝试从文本中找到 JSON 数组
                match = re.search(r'\[.*\]', raw_clean, re.DOTALL)
                if match:
                    try:
                        scored_chunk = json.loads(match.group())
                    except Exception:
                        pass

        if scored_chunk and isinstance(scored_chunk, list):
            for j, s in enumerate(scored_chunk):
                score = s.get("score", 0) if isinstance(s, dict) else 0
                dim   = chunk[j]["dimension"] if j < len(chunk) else "unknown"
                all_scores.append({"dimension": dim, "rubric_item": chunk[j]["text"],
                                    "score": score, "reason": s.get("reason", "") if isinstance(s, dict) else ""})
        else:
            # parse 失败：对该 chunk 全部给 0
            for r in chunk:
                all_scores.append({"dimension": r["dimension"], "rubric_item": r["text"],
                                    "score": 0, "reason": "parse_failed"})

    total      = len(all_scores)
    n_pass     = sum(1 for s in all_scores if s["score"] == 1)
    pass_rate  = n_pass / total if total > 0 else 0.0

    detail = {
        "total_items":  total,
        "passed_items": n_pass,
        "pass_rate":    round(pass_rate, 4),
        "scores":       all_scores,
    }
    return pass_rate, detail


def score_file(framework, bench_key):
    """对单个 (framework, bench_key) 组合评分"""
    infile  = os.path.join(OUTPUT_DIR, f"{framework}_{bench_key}_med.jsonl")
    outfile = os.path.join(SCORED_DIR, f"{framework}_{bench_key}_scored.jsonl")
    metric  = BENCHMARKS[bench_key]

    if not os.path.exists(infile):
        logger.warning(f"文件不存在，跳过: {infile}")
        return None

    # 读取已有评分（断点续跑）
    scored_data = []
    if os.path.exists(outfile):
        with open(outfile, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        scored_data.append(json.loads(line))
                    except Exception:
                        pass
    done_questions = set(item.get("question") for item in scored_data)

    # 读取待评分数据
    data = []
    with open(infile, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except Exception:
                    pass

    to_score = [item for item in data if item.get("question") not in done_questions]
    logger.info(f"[{framework}×{bench_key}] 总={len(data)}, 已评={len(done_questions)}, 待评={len(to_score)}")

    for item in tqdm(to_score, desc=f"Scoring {framework}×{bench_key}"):
        if metric == "accuracy":
            is_correct, judge_result = judge_browsecomp(item)
            scored_item = {**item, "is_correct": is_correct, "judge_result": judge_result}
        elif metric == "f1":
            precision, recall, f1, judge_result = judge_deepsearchqa(item)
            scored_item = {**item, "precision": precision, "recall": recall,
                           "f1": f1, "judge_result": judge_result}
        else:  # rubric (drb2)
            pass_rate, judge_result = judge_drb2_rubric(item)
            scored_item = {**item, "pass_rate": pass_rate, "judge_result": judge_result}

        scored_data.append(scored_item)
        with open(outfile, "a", encoding="utf-8") as f:
            f.write(json.dumps(scored_item, ensure_ascii=False) + "\n")

    # 汇总
    summary = compute_summary(scored_data, metric, framework, bench_key)
    summary_file = os.path.join(SCORED_DIR, f"{framework}_{bench_key}_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info(f"  汇总: {summary}")
    return summary


def compute_summary(scored_data, metric, framework, bench_key):
    """计算汇总指标（先按 task_id 去重，避免重复追加导致统计偏差）"""
    # 按 task_id 去重，保留最后一条（task_id 可能不存在时退化为 question）
    seen = {}
    for item in scored_data:
        key = item.get("task_id") or item.get("question", "")
        seen[key] = item
    scored_data = list(seen.values())
    total = len(scored_data)
    if total == 0:
        return {"framework": framework, "bench": bench_key, "total": 0}

    if metric == "accuracy":
        correct = sum(1 for item in scored_data if item.get("is_correct", False))
        return {
            "framework": framework, "bench": bench_key,
            "total": total, "correct": correct,
            "accuracy": round(correct / total, 4)
        }
    elif metric == "f1":
        avg_f1 = sum(item.get("f1", 0) for item in scored_data) / total
        avg_p  = sum(item.get("precision", 0) for item in scored_data) / total
        avg_r  = sum(item.get("recall", 0) for item in scored_data) / total
        return {
            "framework": framework, "bench": bench_key,
            "total": total,
            "avg_f1":        round(avg_f1, 4),
            "avg_precision": round(avg_p, 4),
            "avg_recall":    round(avg_r, 4),
        }
    else:  # rubric (drb2)
        avg_pass_rate = sum(item.get("pass_rate", 0) for item in scored_data) / total
        return {
            "framework": framework, "bench": bench_key,
            "total": total,
            "avg_pass_rate": round(avg_pass_rate, 4),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frameworks", nargs="+", default=FRAMEWORKS,
                        help="评分框架列表")
    parser.add_argument("--benches",    nargs="+", default=list(BENCHMARKS.keys()),
                        help="评分 benchmark 列表")
    args = parser.parse_args()

    all_summaries = []
    for framework in args.frameworks:
        for bench_key in args.benches:
            s = score_file(framework, bench_key)
            if s:
                all_summaries.append(s)

    print("\n===== 评分汇总 =====")
    for s in all_summaries:
        print(json.dumps(s, ensure_ascii=False))

    # 保存总汇总
    all_summary_file = os.path.join(SCORED_DIR, "all_summaries.json")
    with open(all_summary_file, "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, ensure_ascii=False, indent=2)
    logger.info(f"\n总汇总已保存: {all_summary_file}")


if __name__ == "__main__":
    main()
