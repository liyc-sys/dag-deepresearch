#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step1b_prepare_medical.py
从exp6_medical_subset中采样医学子集数据供DAG评测使用。

选择三个benchmark：
- browsecomp_medical: 医学相关的BrowseComp问题 (171条→采样30条)
- deepsearchqa_medical: 医学相关的DeepSearchQA问题 (147条→采样30条)
- hle_medical: 专家标注的Biology/Medicine问题 (149条→采样30条)
"""
import json
import random
import os

EXP6_BASE = "/mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/X-EvalSuit/work/exp6_medical_subset/assets/output"

MEDICAL_DATASETS = {
    "bc_en_med": {
        "path": f"{EXP6_BASE}/browsecomp/medical_subset.jsonl",
        "sample": 30, "seed": 42,
        "metric": "accuracy",
        "desc": "BrowseComp Medical",
    },
    "dsq_med": {
        "path": f"{EXP6_BASE}/deepsearchqa/medical_subset.jsonl",
        "sample": 30, "seed": 42,
        "metric": "f1",
        "desc": "DeepSearchQA Medical",
    },
    "hle_med": {
        "path": f"{EXP6_BASE}/hle/medical_subset.jsonl",
        "sample": 30, "seed": 42,
        "metric": "accuracy",  # 多选题，按正确率
        "desc": "HLE Biology/Medicine",
    },
}

OUT_DIR = os.path.join(os.path.dirname(__file__), "assets/input")
os.makedirs(OUT_DIR, exist_ok=True)


def read_jsonl(path):
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def write_jsonl(path, data):
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main():
    for name, cfg in MEDICAL_DATASETS.items():
        print(f"\n[{name}] 读取: {cfg['path']}")
        data = read_jsonl(cfg["path"])
        print(f"  总条数: {len(data)}")

        # 随机采样
        rng = random.Random(cfg["seed"])
        sampled = rng.sample(data, min(cfg["sample"], len(data)))
        print(f"  采样后: {len(sampled)} 条")

        # 字段转换：task_question → question, ground_truth → answer
        converted = []
        for item in sampled:
            converted.append({
                "question": item["task_question"],
                "answer": item.get("ground_truth", ""),
                "task_id": item.get("task_id", ""),
                "metadata": item.get("metadata", {}),
                "is_medical": item.get("is_medical", True),
                "medical_reason": item.get("medical_reason", ""),
            })

        out_path = os.path.join(OUT_DIR, f"{name}_30.jsonl")
        write_jsonl(out_path, converted)
        print(f"  已保存: {out_path}")

        for i, item in enumerate(converted[:2]):
            print(f"  样本{i}: Q={item['question'][:60]}... A={item['answer'][:30]}")

    print("\n[完成] 医学子集数据准备完毕")


if __name__ == "__main__":
    main()
