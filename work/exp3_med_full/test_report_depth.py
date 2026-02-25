#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 report 框架的两种深度模式"""

import os
import sys
import json

# 在导入前设置环境变量
os.environ["OPENAI_API_KEY"] = "bb6ce7bb-dcd3-4733-9f13-ada2de86ef11"
os.environ["OPENAI_API_BASE"] = "https://ark-cn-beijing.bytedance.net/api/v3"
os.environ["SERPER_API_KEY"] = "af31ec29fabd1854a3cc34da3b5324d47ba55168"
os.environ["JINA_API_KEY"] = "jina_21ed3799312248a7a1aa73b549bd44f1N3Lm4OdyW66asT108Uu55M83cZh0"
os.environ["DEFAULT_MODEL"] = "ep-20250724221742-fddgp"

DAG_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, DAG_ROOT)

from step2_run_eval import process_item_report

# 测试数据：一个简单的问题
test_item_lite = {
    "question": "What is the capital of France?",
    "answer": "Paris",
    "task_id": "test_lite",
    "bench": "test",
    "metric": "accuracy",
}

test_item_full = {
    "question": "Explain the historical significance of the Eiffel Tower and its impact on French culture.",
    "answer": "The Eiffel Tower is a symbol of French culture and engineering achievement...",
    "task_id": "test_full",
    "bench": "test",
    "metric": "rubric",
}

print("=" * 80)
print("测试 Report 框架 - LITE 模式（适合 accuracy/F1 评分）")
print("=" * 80)
print(f"问题：{test_item_lite['question']}")
print()

result_lite = process_item_report(test_item_lite, depth="lite", summary_interval=6)

if result_lite:
    print("=" * 80)
    print("LITE 模式结果")
    print("=" * 80)
    print(f"Agent答案：{result_lite['agent_result']}")
    print(f"总耗时：{result_lite['total_time']:.1f}s")
    print(f"Token消耗：输入={result_lite['input_tokens']}, 输出={result_lite['output_tokens']}")
    print(f"报告长度：{len(result_lite['report'])} 字符")
    print()

print("\n" + "=" * 80)
print("测试 Report 框架 - FULL 模式（适合 rubric 评分）")
print("=" * 80)
print(f"问题：{test_item_full['question'][:100]}...")
print()

result_full = process_item_report(test_item_full, depth="full", summary_interval=6)

if result_full:
    print("=" * 80)
    print("FULL 模式结果")
    print("=" * 80)
    print(f"Agent答案：{result_full['agent_result'][:200]}...")
    print(f"总耗时：{result_full['total_time']:.1f}s")
    print(f"Token消耗：输入={result_full['input_tokens']}, 输出={result_full['output_tokens']}")
    print(f"报告长度：{len(result_full['report'])} 字符")
    print()

# 对比
print("=" * 80)
print("对比总结")
print("=" * 80)
if result_lite and result_full:
    print(f"LITE vs FULL:")
    print(f"  耗时: {result_lite['total_time']:.1f}s vs {result_full['total_time']:.1f}s (比例: {result_full['total_time']/result_lite['total_time']:.1f}x)")
    print(f"  Token: {result_lite['input_tokens']+result_lite['output_tokens']} vs {result_full['input_tokens']+result_full['output_tokens']} (比例: {(result_full['input_tokens']+result_full['output_tokens'])/(result_lite['input_tokens']+result_lite['output_tokens']):.1f}x)")
    print(f"  报告长度: {len(result_lite['report'])} vs {len(result_full['report'])} (比例: {len(result_full['report'])/len(result_lite['report']):.1f}x)")
