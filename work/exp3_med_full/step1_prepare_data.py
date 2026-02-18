#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step1_prepare_data.py
从各医学 benchmark 的 medical_subset.csv 中采样数据。

整体逻辑：
1. 读取每个 benchmark 的 medical_subset.csv（字段：task_id, task_question, ground_truth, ...）
2. 每个 benchmark 采样最多 50 条（不足50条全取），随机种子=42
3. 输出：assets/input/{bench_key}_med.jsonl，字段：question, answer, task_id, bench, metadata
"""
import os
import csv
import json
import random
import argparse

MIRO_DATA_DIR = "/mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/miro/MiroFlow/data"

# bench_key -> {dir, metric, sample_size}
BENCHMARKS = {
    "bc_en_med": {"dir": "browsecomp-test",    "metric": "accuracy", "sample": 50},
    "bc_zh_med": {"dir": "browsecomp-zh-test", "metric": "accuracy", "sample": 30},  # 只有30条
    "dsq_med":   {"dir": "deepsearchqa",        "metric": "f1",       "sample": 50},
    "drb_med":   {"dir": "drb",                 "metric": "accuracy", "sample": 50},
    "gaia_med":  {"dir": "gaia-val",            "metric": "accuracy", "sample": 50},
    "hle_med":   {"dir": "hle",                 "metric": "accuracy", "sample": 50},
    "drb2_med":  {"dir": "drb2",                "metric": "rubric",   "sample": 12},  # 全取12条
    "xbench_med":{"dir": "xbench-ds",           "metric": "accuracy", "sample": 50},
}

EXP_DIR   = os.path.dirname(__file__)
INPUT_DIR = os.path.join(EXP_DIR, "assets/input")
os.makedirs(INPUT_DIR, exist_ok=True)


def load_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sample_rows(rows, n, seed=42):
    if len(rows) <= n:
        return rows
    rng = random.Random(seed)
    return rng.sample(rows, n)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benches", nargs="+", default=list(BENCHMARKS.keys()),
                        help="要处理的 benchmark key 列表")
    args = parser.parse_args()

    for bench_key in args.benches:
        cfg = BENCHMARKS[bench_key]
        csv_path = os.path.join(MIRO_DATA_DIR, cfg["dir"], "medical_subset.csv")
        if not os.path.exists(csv_path):
            print(f"[SKIP] {bench_key}: CSV 不存在 {csv_path}")
            continue

        rows = load_csv(csv_path)
        sampled = sample_rows(rows, cfg["sample"])
        print(f"{bench_key}: 总={len(rows)}, 采样={len(sampled)}")

        out_path = os.path.join(INPUT_DIR, f"{bench_key}_med.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for row in sampled:
                # 保留所有 CSV 字段作为 metadata
                metadata = {k: v for k, v in row.items()
                            if k not in ("task_id", "task_question", "ground_truth")}
                # drb2: ground_truth 是 rubric JSON 字符串，放到 metadata["rubric"] 中便于 step4 使用
                answer = row["ground_truth"]
                if bench_key == "drb2_med":
                    try:
                        metadata["rubric"] = json.loads(answer)
                    except Exception:
                        metadata["rubric"] = answer
                item = {
                    "question":  row["task_question"],
                    "answer":    answer,
                    "task_id":   str(row["task_id"]),
                    "bench":     bench_key,
                    "metric":    cfg["metric"],
                    "metadata":  metadata,
                }
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        print(f"  -> {out_path} ({len(sampled)} 条)")

    print("\n[完成] 数据准备完毕")


if __name__ == "__main__":
    main()
