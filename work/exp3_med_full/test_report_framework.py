#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 report 框架（ReportOrchestrator）在单个样本上的表现"""

import os
import sys
import json

# ===== 重要：在导入任何模块之前设置环境变量 =====
os.environ["OPENAI_API_KEY"] = "bb6ce7bb-dcd3-4733-9f13-ada2de86ef11"
os.environ["OPENAI_API_BASE"] = "https://ark-cn-beijing.bytedance.net/api/v3"
os.environ["SERPER_API_KEY"] = "af31ec29fabd1854a3cc34da3b5324d47ba55168"
os.environ["JINA_API_KEY"] = "jina_21ed3799312248a7a1aa73b549bd44f1N3Lm4OdyW66asT108Uu55M83cZh0"
os.environ["DEFAULT_MODEL"] = "ep-20250724221742-fddgp"

# 指向 dag-deepresearch 根目录
DAG_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, DAG_ROOT)

# 导入处理函数
from step2_run_eval import process_item_report

# 测试数据
test_item = {
    "question": "这是一种化学物质，首次于1965年被发现，其英文名中含有一个字母's'，该化学物质的化学式中含有四种不同的元素，并且摩尔质量在290到300之间。提问：该化学物质的中文化学名是？",
    "answer": "天冬氨酰苯丙氨酸甲酯 or 天门冬胺酰苯丙氨酸甲酯 or 天门冬酰苯丙氨酸甲酯",
    "task_id": "21",
    "bench": "bc_zh_med",
    "metric": "accuracy",
}

print("=" * 80)
print("测试 Report 框架（ReportOrchestrator）")
print("=" * 80)
print(f"问题：{test_item['question'][:100]}...")
print(f"正确答案：{test_item['answer']}")
print()

# 运行推理
result = process_item_report(
    test_item,
    max_section_steps=10,
    section_concurrency=3,
    summary_interval=6
)

if result:
    print("=" * 80)
    print("推理结果")
    print("=" * 80)
    print(f"Agent答案：{result['agent_result']}")
    print()
    print(f"报告长度：{len(result['report'])} 字符")
    print(f"总耗时：{result['total_time']:.1f}s")
    print(f"Token消耗：输入={result['input_tokens']}, 输出={result['output_tokens']}")
    print()
    print("=" * 80)
    print("完整报告（前1000字符）")
    print("=" * 80)
    print(result['report'][:1000])
    print("\n...\n")
    print("=" * 80)
    print("完整报告（最后500字符）")
    print("=" * 80)
    print(result['report'][-500:])

    # 保存完整结果
    with open("/tmp/test_report_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n完整结果已保存到：/tmp/test_report_result.json")
else:
    print("❌ 推理失败")
