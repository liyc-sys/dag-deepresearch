#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step1_prepare_data.py
从三个benchmark中采样50条数据，转换字段格式供dag-deepresearch使用。
输入字段：task_question, ground_truth
输出字段：question, answer (+ 保留task_id, metadata)
"""
import json
import random
import os

# ===== 数据集配置 =====
DATASETS = {
    "bc_en": {
        "path": "/mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/MiroFlow/data/browsecomp-test/standardized_data.jsonl",
        "sample": 50,
        "seed": 42,
        "metric": "accuracy",
        "desc": "BrowseComp English"
    },
    "bc_zh": {
        "path": "/mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/X-EvalSuit/work/exp9_merge_swalm/assets/input/browsecomp_zh_clean.jsonl",
        "sample": 50,
        "seed": 42,
        "metric": "accuracy",
        "desc": "BrowseComp Chinese"
    },
    "dsq": {
        "path": "/mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/MiroFlow/data/deepsearchqa/standardized_data.jsonl",
        "sample": 50,
        "seed": 42,
        "metric": "f1",
        "desc": "DeepSearchQA"
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
    for name, cfg in DATASETS.items():
        print(f"\n[{name}] 读取数据集: {cfg['path']}")
        data = read_jsonl(cfg["path"])
        print(f"  总条数: {len(data)}")

        # 随机采样（保证与swalm实验一致，seed=42）
        rng = random.Random(cfg["seed"])
        sampled = rng.sample(data, min(cfg["sample"], len(data)))
        print(f"  采样后: {len(sampled)} 条")

        # 字段转换
        converted = []
        for item in sampled:
            converted.append({
                "question": item["task_question"],
                "answer": item["ground_truth"],
                "task_id": item.get("task_id", ""),
                "metadata": item.get("metadata", {}),
            })

        out_path = os.path.join(OUT_DIR, f"{name}_50.jsonl")
        write_jsonl(out_path, converted)
        print(f"  已保存: {out_path}")

        # 打印前2条样本
        for i, item in enumerate(converted[:2]):
            print(f"  样本{i}: Q={item['question'][:60]}... A={item['answer']}")

    print("\n[完成] 所有数据集准备完毕")


if __name__ == "__main__":
    main()
