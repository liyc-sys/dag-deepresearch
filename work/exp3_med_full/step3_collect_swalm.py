#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step3_collect_swalm.py
从已有的 SWALM seed16 结果中按 task_id 匹配，提取对应条目并转换为统一格式。

整体逻辑：
1. 读取 step1 生成的 50 条子集（获取 task_id 列表和问题信息）
2. 从 SWALM results/{bench}_seed16/details.jsonl 中按 task_id 匹配
3. 转换为统一格式：question, golden_answer, agent_result(=prediction), task_id, bench, metric, metadata
4. 输出：assets/output/swalm_{bench_key}_med.jsonl

注意：SWALM 已按医学子集全量运行，通过 task_id 匹配采样的50条。
"""
import os
import json
import argparse

SWALM_BASE = "/mnt/bn/med-mllm-lfv2/linjh/project/learn/2026_q1/eval/X-EvalSuit/repo/swalm_agent/evals/test_results"

# bench_key -> SWALM 目录名（不含 _seed16 后缀）
# 注：drb2_med 是新 benchmark，无 SWALM 基线结果
SWALM_BENCH_MAP = {
    "bc_en_med": "browsecomp",
    "bc_zh_med": "browsecomp-zh",
    "dsq_med":   "deepsearchqa",
    "drb_med":   "drb",
    "gaia_med":  "gaia",
    "hle_med":   "hle",
    "xbench_med":"xbench",
}

EXP_DIR    = os.path.dirname(__file__)
INPUT_DIR  = os.path.join(EXP_DIR, "assets/input")
OUTPUT_DIR = os.path.join(EXP_DIR, "assets/output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


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


def load_swalm_results(swalm_dir):
    """加载 SWALM 结果，返回 task_id -> record 的字典"""
    details_path = os.path.join(swalm_dir, "details.jsonl")
    if not os.path.exists(details_path):
        return {}
    records = read_jsonl(details_path)
    return {str(r["task_id"]): r for r in records}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benches", nargs="+", default=list(SWALM_BENCH_MAP.keys()),
                        help="要处理的 benchmark key 列表")
    args = parser.parse_args()

    for bench_key in args.benches:
        if bench_key not in SWALM_BENCH_MAP:
            print(f"[SKIP] {bench_key}: 未在 SWALM_BENCH_MAP 中")
            continue

        # 读取 step1 生成的子集
        infile = os.path.join(INPUT_DIR, f"{bench_key}_med.jsonl")
        subset = read_jsonl(infile)
        if not subset:
            print(f"[SKIP] {bench_key}: 输入文件不存在或为空 {infile}")
            continue

        # 加载 SWALM 结果
        swalm_dir_name = f"{SWALM_BENCH_MAP[bench_key]}_seed16"
        swalm_dir = os.path.join(SWALM_BASE, swalm_dir_name)
        swalm_map = load_swalm_results(swalm_dir)

        if not swalm_map:
            print(f"[WARN] {bench_key}: SWALM 结果为空 {swalm_dir}")
            continue

        # 按 task_id 匹配
        outfile = os.path.join(OUTPUT_DIR, f"swalm_{bench_key}_med.jsonl")
        matched = 0
        unmatched_ids = []

        with open(outfile, "w", encoding="utf-8") as fout:
            for item in subset:
                tid = str(item["task_id"])
                swalm_rec = swalm_map.get(tid)
                if swalm_rec is None:
                    unmatched_ids.append(tid)
                    continue

                # 转换为统一格式
                out_item = {
                    "question":      item["question"],
                    "golden_answer": item["answer"],
                    "agent_result":  swalm_rec.get("prediction", ""),
                    "task_id":       tid,
                    "bench":         bench_key,
                    "metric":        item.get("metric", "accuracy"),
                    "metadata":      item.get("metadata", {}),
                    # 保留 SWALM 原始字段用于参考
                    "swalm_is_correct": swalm_rec.get("is_correct"),
                    "swalm_score":      swalm_rec.get("score"),
                }
                fout.write(json.dumps(out_item, ensure_ascii=False) + "\n")
                matched += 1

        print(f"{bench_key}: 子集={len(subset)}, 匹配={matched}, 未匹配={len(unmatched_ids)}")
        if unmatched_ids:
            print(f"  未匹配的 task_id: {unmatched_ids[:10]}")
        print(f"  -> {outfile}")

    print("\n[完成] SWALM 结果收集完毕")


if __name__ == "__main__":
    main()
