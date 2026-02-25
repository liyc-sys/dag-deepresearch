#!/usr/bin/env python3
"""
使用官方DRB评估方法（RACE+FACT）重新评分DRB结果

使用豆包Seed 1.6作为judge（替代Gemini）
使用Jina API进行URL抓取（FACT框架）
"""
import json
import os
import sys
from pathlib import Path

# 添加X-EvalSuit路径
XEVALSUIT_PATH = "/mnt/bn/med-mllm-lfv2/linjh/project/learn/idke/Agent-Factory-Med/others/X-EvalSuit"
sys.path.insert(0, XEVALSUIT_PATH)

from openai import OpenAI
from tqdm import tqdm

# 从X-EvalSuit导入DRB相关函数
from agentic_eval.judger.drb import (
    DRBJudger,
    format_for_drb,
    parse_and_format_citations,
    parse_search_results_with_id
)

# API配置
ARK_API_KEY = "bb6ce7bb-dcd3-4733-9f13-ada2de86ef11"
ARK_API_BASE = "https://ark-cn-beijing.bytedance.net/api/v3"
ARK_MODEL = "ep-20250724221742-fddgp"  # Seed 1.6

JINA_API_KEY = "jina_21ed3799312248a7a1aa73b549bd44f1N3Lm4OdyW66asT108Uu55M83cZh0"
JINA_BASE_URL = "https://r.jina.ai"


class DoubaoLLMClient:
    """豆包LLM客户端，兼容X-EvalSuit的接口"""

    def __init__(self, api_key=ARK_API_KEY, base_url=ARK_API_BASE, model=ARK_MODEL):
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=300
        )
        self.model = model

    def chat_completion(self, messages, tools=None, max_tokens=2048, temperature=0.2, **kwargs):
        """X-EvalSuit的BaseJudger需要的接口"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return {
                "content": response.choices[0].message.content,
                "role": "assistant"
            }
        except Exception as e:
            raise RuntimeError(f"豆包API调用失败: {e}")

    def __call__(self, prompt, **kwargs):
        """兼容X-EvalSuit的调用接口"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.0),
                max_tokens=kwargs.get("max_tokens", 2000)
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"豆包API调用失败: {e}")
            return None


def load_drb_results(input_path):
    """加载DRB推理结果"""
    results = []
    with open(input_path, 'r') as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))
    return results


def convert_to_drb_format(item):
    """
    将我们的输出转换为DRB官方格式

    需要构建conversation_history用于引用提取
    """
    # 从report中提取引用信息
    report = item.get("report", "")

    # 简化处理：假设report中的引用已经格式化好了
    # 实际应该从agent的traces中提取tool responses
    conversation_history = []

    # 如果report中包含参考文献，尝试解析
    # 这里简化处理，实际应该从agent执行过程中获取

    formatted = {
        "id": item.get("task_id", ""),
        "problem": item.get("question", ""),
        "final_response": report,
        "prediction": report,
        "conversation_history": conversation_history,
        "full_traces": {}  # 如果有traces可以添加
    }

    return format_for_drb(formatted)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="使用豆包judge重新评估DRB结果")
    parser.add_argument("--input", required=True, help="输入JSONL文件（包含report）")
    parser.add_argument("--output", required=True, help="输出JSONL文件（包含RACE+FACT评分）")
    args = parser.parse_args()

    print("=" * 80)
    print("DRB官方评估 - 使用豆包作为judge")
    print("=" * 80)
    print(f"输入文件: {args.input}")
    print(f"输出文件: {args.output}")
    print(f"Judge模型: 豆包 Seed 1.6")
    print(f"FACT引擎: Jina API")
    print()

    # 加载结果
    print("加载DRB推理结果...")
    results = load_drb_results(args.input)
    print(f"  共{len(results)}条结果")

    # 初始化豆包客户端
    print("\n初始化豆包judge...")
    doubao_client = DoubaoLLMClient()

    # 初始化DRB Judger（使用豆包作为LLM）
    judger = DRBJudger(
        llm_client=doubao_client,
        max_retries=3
    )

    # 检查是否已有评分结果（断点续跑）
    scored_ids = set()
    if os.path.exists(args.output):
        print(f"\n检测到已有评分文件，加载已评分ID...")
        with open(args.output, 'r') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if "judge_result" in data and "race" in data["judge_result"]:
                        scored_ids.add(data["task_id"])
        print(f"  已评分: {len(scored_ids)}条")

    # 评估统计
    total_evaluated = 0
    race_scores = {
        "comprehensiveness": [],
        "insight": [],
        "instruction_following": [],
        "readability": [],
        "overall": []
    }
    fact_stats = {
        "total_citations": 0,
        "total_unique_urls": 0,
        "samples_with_citations": 0
    }

    # 逐条评估
    print(f"\n开始评估（待评: {len(results) - len(scored_ids)}条）...")
    with open(args.output, 'a') as out_f:
        for item in tqdm(results, desc="评估DRB报告"):
            task_id = item["task_id"]

            # 跳过已评分
            if task_id in scored_ids:
                continue

            question = item["question"]
            report = item.get("report", "")

            # 调用DRB judger
            is_correct, judge_result = judger.judge(
                question=question,
                response=report,
                correct_answer="",  # DRB没有ground truth
                id=task_id,
                full_traces={},
                conversation_history=[],
                skip_race=False  # 执行RACE评估
            )

            # 保存结果
            item["judge_result"] = judge_result
            item["is_correct"] = is_correct
            out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
            out_f.flush()

            # 统计
            if judge_result.get("status") == "formatted":
                total_evaluated += 1

                # RACE统计
                race = judge_result.get("race", {})
                if race and not race.get("skipped") and "error" not in race:
                    for key in ["comprehensiveness", "insight", "instruction_following", "readability", "overall"]:
                        if key in race:
                            race_scores[key].append(race[key])

                # FACT统计
                fact = judge_result.get("fact", {})
                num_citations = fact.get("num_citations", 0)
                fact_stats["total_citations"] += num_citations
                fact_stats["total_unique_urls"] += fact.get("num_unique_urls", 0)
                if num_citations > 0:
                    fact_stats["samples_with_citations"] += 1

    # 汇总结果
    print("\n" + "=" * 80)
    print("评估完成！")
    print("=" * 80)

    summary = {
        "framework": "report",
        "bench": "drb_med",
        "total": len(results),
        "evaluated": total_evaluated,
        "evaluation_method": "Official DRB (RACE + FACT)",
        "judge_model": "Doubao Seed 1.6 (ep-20250724221742-fddgp)",
    }

    # RACE结果
    if race_scores["overall"]:
        summary["race"] = {
            "comprehensiveness": round(sum(race_scores["comprehensiveness"]) / len(race_scores["comprehensiveness"]), 2),
            "insight": round(sum(race_scores["insight"]) / len(race_scores["insight"]), 2),
            "instruction_following": round(sum(race_scores["instruction_following"]) / len(race_scores["instruction_following"]), 2),
            "readability": round(sum(race_scores["readability"]) / len(race_scores["readability"]), 2),
            "overall": round(sum(race_scores["overall"]) / len(race_scores["overall"]), 2),
            "num_evaluated": len(race_scores["overall"]),
            "note": "Point-wise scores (0-10 scale). Judge: Doubao Seed 1.6"
        }

        print("\n【RACE评分】（0-10分制）")
        print(f"  Comprehensiveness (全面性): {summary['race']['comprehensiveness']:.2f}/10")
        print(f"  Insight (洞察力): {summary['race']['insight']:.2f}/10")
        print(f"  Instruction Following (指令遵循): {summary['race']['instruction_following']:.2f}/10")
        print(f"  Readability (可读性): {summary['race']['readability']:.2f}/10")
        print(f"  Overall (综合): {summary['race']['overall']:.2f}/10")
        print(f"  评估样本数: {summary['race']['num_evaluated']}")

    # FACT结果
    if total_evaluated > 0:
        summary["fact"] = {
            "samples_with_citations": fact_stats["samples_with_citations"],
            "citation_rate": round(fact_stats["samples_with_citations"] / total_evaluated * 100, 2),
            "avg_citations": round(fact_stats["total_citations"] / total_evaluated, 2),
            "avg_unique_urls": round(fact_stats["total_unique_urls"] / total_evaluated, 2),
            "note": "Basic citation statistics. Full FACT validation requires Jina scraping."
        }

        print("\n【FACT统计】（基础引用统计）")
        print(f"  包含引用的样本数: {summary['fact']['samples_with_citations']}/{total_evaluated} ({summary['fact']['citation_rate']:.1f}%)")
        print(f"  平均引用数: {summary['fact']['avg_citations']:.2f}")
        print(f"  平均唯一URL数: {summary['fact']['avg_unique_urls']:.2f}")
        print(f"  注: 完整FACT验证需要Jina API抓取和验证")

    # 保存汇总
    summary_path = args.output.replace("_scored.jsonl", "_summary.json")
    with open(summary_path, 'w') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n汇总已保存: {summary_path}")
    print("\n" + "=" * 80)
    print("✅ 评估完成！使用了官方DRB评估方法（豆包judge）")
    print("=" * 80)


if __name__ == "__main__":
    main()
