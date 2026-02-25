#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step3_score.py
对dag-deepresearch的推理结果进行评分。

整体逻辑：
1. BrowseComp (bc_en, bc_zh): 使用LLM judge判断回答是否正确，指标=Accuracy
2. DeepSearchQA (dsq): 使用LLM judge判断每个答案片段是否正确，计算P/R/F1

评分使用GPT-4.1（字节内部代理）作为Judge，与swalm实验保持一致。
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

MODELS   = ["seed16", "seed18", "gpt41"]
DATASETS = {
    "bc_en":     "accuracy",
    "bc_zh":     "accuracy",
    "dsq":       "f1",
    "bc_en_med": "accuracy",
    "dsq_med":   "f1",
    "hle_med":   "accuracy",
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
    """调用GPT-4.1作为judge"""
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
    """从文本中提取JSON"""
    if not text:
        return None
    # 去掉markdown代码块
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
    """BrowseComp评分：LLM judge返回is_correct"""
    question  = item.get("question", "")
    golden    = item.get("golden_answer", "")
    response  = item.get("agent_result", "")

    if not response:
        return False, {"error": "no agent_result"}

    prompt = BC_JUDGE_PROMPT.format(
        question=question,
        correct_answer=golden,
        response=str(response)[:3000]
    )
    raw = call_judge(prompt)
    parsed = parse_json_from_text(raw)
    if parsed:
        is_correct = bool(parsed.get("is_correct", False))
        return is_correct, parsed
    return False, {"raw": raw, "error": "parse_failed"}


def judge_deepsearchqa(item):
    """DeepSearchQA评分：计算P/R/F1"""
    question  = item.get("question", "")
    golden    = item.get("golden_answer", "")
    response  = item.get("agent_result", "")
    metadata  = item.get("metadata", {})
    prompt_type = metadata.get("answer_type", "Single Answer")

    if not response:
        return 0.0, 0.0, 0.0, {"error": "no agent_result"}

    prompt = DSQ_JUDGE_PROMPT.format(
        prompt_type=prompt_type,
        prompt=question,
        answer=golden,
        response=str(response)[:3000]
    )
    raw = call_judge(prompt)
    parsed = parse_json_from_text(raw)

    try:
        ac = parsed["Answer Correctness"]
        details = ac.get("Correctness Details", {})
        excessive = ac.get("Excessive Answers", [])

        correct_count = sum(1 for v in details.values() if v)
        total_expected = len(details)
        total_predicted = correct_count + len(excessive)

        precision = correct_count / total_predicted if total_predicted > 0 else 0.0
        recall    = correct_count / total_expected  if total_expected > 0 else 0.0
        f1        = (2 * precision * recall / (precision + recall)
                     if precision + recall > 0 else 0.0)
        return precision, recall, f1, parsed
    except Exception as e:
        return 0.0, 0.0, 0.0, {"raw": raw, "error": str(e)}


def score_file(model_key, dataset_key):
    """对单个(model, dataset)组合评分"""
    infile  = os.path.join(OUTPUT_DIR, f"{model_key}_{dataset_key}.jsonl")
    outfile = os.path.join(SCORED_DIR, f"{model_key}_{dataset_key}_scored.jsonl")
    metric  = DATASETS[dataset_key]

    if not os.path.exists(infile):
        logger.warning(f"文件不存在: {infile}")
        return None

    # 读取已有评分（断点续跑）
    scored_data = []
    if os.path.exists(outfile):
        scored_data = []
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
    logger.info(f"[{model_key}×{dataset_key}] 总={len(data)}, 已评={len(done_questions)}, 待评={len(to_score)}")

    for item in tqdm(to_score, desc=f"Scoring {model_key}×{dataset_key}"):
        if metric == "accuracy":
            is_correct, judge_result = judge_browsecomp(item)
            scored_item = {**item, "is_correct": is_correct, "judge_result": judge_result}
        else:  # f1
            precision, recall, f1, judge_result = judge_deepsearchqa(item)
            scored_item = {**item, "precision": precision, "recall": recall,
                           "f1": f1, "judge_result": judge_result}

        scored_data.append(scored_item)
        with open(outfile, "a", encoding="utf-8") as f:
            f.write(json.dumps(scored_item, ensure_ascii=False) + "\n")

    # 汇总结果
    summary = compute_summary(scored_data, metric, model_key, dataset_key)
    summary_file = os.path.join(SCORED_DIR, f"{model_key}_{dataset_key}_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info(f"  汇总: {summary}")
    return summary


def compute_summary(scored_data, metric, model_key, dataset_key):
    """计算汇总指标"""
    total = len(scored_data)
    if total == 0:
        return {"model": model_key, "dataset": dataset_key, "total": 0}

    if metric == "accuracy":
        correct = sum(1 for item in scored_data if item.get("is_correct", False))
        return {
            "model": model_key, "dataset": dataset_key,
            "total": total, "correct": correct,
            "accuracy": round(correct / total, 4)
        }
    else:  # f1
        avg_f1 = sum(item.get("f1", 0) for item in scored_data) / total
        avg_p  = sum(item.get("precision", 0) for item in scored_data) / total
        avg_r  = sum(item.get("recall", 0) for item in scored_data) / total
        return {
            "model": model_key, "dataset": dataset_key,
            "total": total,
            "avg_f1": round(avg_f1, 4),
            "avg_precision": round(avg_p, 4),
            "avg_recall": round(avg_r, 4),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models",   nargs="+", default=MODELS)
    parser.add_argument("--datasets", nargs="+", default=list(DATASETS.keys()))
    args = parser.parse_args()

    all_summaries = []
    for model_key in args.models:
        for dataset_key in args.datasets:
            s = score_file(model_key, dataset_key)
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
