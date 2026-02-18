#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
final_analysis.py
等所有推理+评分完成后，自动生成完整对比分析，更新报告 MD。

整体逻辑：
1. 读取所有 summary.json 文件
2. 生成完整对比表格（4框架 × 8benchmark）
3. 分析 DAG vs DAG-Med 的提升/下降
4. 比较 planning 质量指标（步数、Goal数、planning时间）
5. 更新 docs/dag_analysis_report.md 中待补充部分
"""
import os
import json
import statistics

EXP_DIR = os.path.dirname(os.path.dirname(__file__))
SCORED_DIR = os.path.join(EXP_DIR, "assets/output/scored")
OUTPUT_DIR = os.path.join(EXP_DIR, "assets/output")

FRAMEWORKS = ["swalm", "flashsearcher", "dag", "dag_med"]
FRAMEWORK_LABELS = {
    "swalm":        "SWALM+Seed16",
    "flashsearcher":"FlashSearcher+Seed16",
    "dag":          "DAG (default)",
    "dag_med":      "DAG-Med (medical)",
}

BENCHMARKS = [
    ("bc_en_med",  "accuracy", "BC-EN"),
    ("bc_zh_med",  "accuracy", "BC-ZH"),
    ("dsq_med",    "f1",       "DSQ(F1)"),
    ("drb_med",    "accuracy", "DRB"),
    ("gaia_med",   "accuracy", "GAIA"),
    ("hle_med",    "accuracy", "HLE"),
    ("drb2_med",   "rubric",   "DRB2(Rubric)"),
    ("xbench_med", "accuracy", "XBench"),
]


def load_summaries():
    summaries = {}
    if not os.path.exists(SCORED_DIR):
        return summaries
    for fname in os.listdir(SCORED_DIR):
        if not fname.endswith("_summary.json"):
            continue
        stem = fname.replace("_summary.json", "")
        for fw in FRAMEWORKS:
            if stem.startswith(fw + "_"):
                bench_key = stem[len(fw) + 1:]
                path = os.path.join(SCORED_DIR, fname)
                with open(path) as f:
                    summaries[(fw, bench_key)] = json.load(f)
                break
    return summaries


def get_score(summary, metric):
    if not summary:
        return None
    if metric == "f1":
        return summary.get("avg_f1")
    elif metric == "rubric":
        return summary.get("avg_pass_rate")
    else:
        return summary.get("accuracy")


def analyze_trajectories():
    """分析各框架的 trajectory 统计（步数、planning时间、goal数）"""
    results = {}
    for fw in ["dag", "dag_med"]:
        fw_stats = {}
        for bench_key, metric, _ in BENCHMARKS:
            path = os.path.join(OUTPUT_DIR, f"{fw}_{bench_key}_med.jsonl")
            if not os.path.exists(path):
                continue
            items = []
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            items.append(json.loads(line))
                        except:
                            pass
            if not items:
                continue

            plan_times, step_counts, goal_counts = [], [], []
            for item in items:
                traj = item.get("agent_trajectory", [])
                plan_step = next((s for s in traj if s.get("name") == "plan"), None)
                if plan_step:
                    plan_times.append(plan_step.get("duration", 0))
                    goals = plan_step.get("value", "").count("## Goal ")
                    goal_counts.append(goals)
                step_counts.append(len(traj))

            fw_stats[bench_key] = {
                "n": len(items),
                "avg_steps": statistics.mean(step_counts) if step_counts else 0,
                "avg_plan_time": statistics.mean(plan_times) if plan_times else 0,
                "avg_goals": statistics.mean(goal_counts) if goal_counts else 0,
            }
        results[fw] = fw_stats
    return results


def print_comparison_table(summaries):
    print("\n" + "=" * 100)
    print("完整对比表格")
    print("=" * 100)

    # 表头
    bench_labels = [b[2] for b in BENCHMARKS]
    header = f"{'Framework':<22}" + "".join(f"{lb:>12}" for lb in bench_labels) + f"{'AVG':>10}"
    print(header)
    print("-" * 100)

    for fw in FRAMEWORKS:
        scores = []
        row = f"{FRAMEWORK_LABELS[fw]:<22}"
        for bench_key, metric, label in BENCHMARKS:
            s = summaries.get((fw, bench_key))
            score = get_score(s, metric)
            if score is not None:
                scores.append(score * 100)
                row += f"{score * 100:>12.1f}%"
            else:
                row += f"{'—':>12}"
        if scores:
            avg = sum(scores) / len(scores)
            row += f"{avg:>10.1f}%"
        else:
            row += f"{'—':>10}"
        print(row)

    print("=" * 100)


def print_dag_vs_dagmed(summaries):
    print("\n" + "=" * 80)
    print("DAG vs DAG-Med 对比（提升为 +，下降为 -）")
    print("=" * 80)
    print(f"{'Benchmark':<15} {'DAG':>8} {'DAG-Med':>10} {'Delta':>8} {'Winner'}")
    print("-" * 80)

    total_delta = []
    for bench_key, metric, label in BENCHMARKS:
        dag_s = summaries.get(("dag", bench_key))
        med_s = summaries.get(("dag_med", bench_key))
        dag_score = get_score(dag_s, metric)
        med_score = get_score(med_s, metric)

        if dag_score is None and med_score is None:
            print(f"{label:<15} {'—':>8} {'—':>10}")
            continue

        dag_str = f"{dag_score*100:.1f}%" if dag_score is not None else "—"
        med_str = f"{med_score*100:.1f}%" if med_score is not None else "—"

        if dag_score is not None and med_score is not None:
            delta = (med_score - dag_score) * 100
            total_delta.append(delta)
            winner = "DAG-Med ▲" if delta > 0.5 else ("DAG ▼" if delta < -0.5 else "Draw")
            delta_str = f"{delta:+.1f}%"
        else:
            delta_str = "—"
            winner = "—"

        print(f"{label:<15} {dag_str:>8} {med_str:>10} {delta_str:>8}  {winner}")

    if total_delta:
        print("-" * 80)
        avg_delta = sum(total_delta) / len(total_delta)
        print(f"{'Average':<15} {'':>8} {'':>10} {avg_delta:>+8.2f}%")
    print("=" * 80)


def print_trajectory_stats(traj_stats):
    print("\n" + "=" * 80)
    print("Trajectory 效率对比（DAG vs DAG-Med）")
    print("=" * 80)
    print(f"{'Benchmark':<15} {'DAG Steps':>12} {'Med Steps':>12} {'DAG Goals':>12} {'Med Goals':>12} {'DAG Plan(s)':>12} {'Med Plan(s)':>12}")
    print("-" * 80)

    dag_stats = traj_stats.get("dag", {})
    med_stats = traj_stats.get("dag_med", {})

    for bench_key, metric, label in BENCHMARKS:
        d = dag_stats.get(bench_key)
        m = med_stats.get(bench_key)
        d_steps = f"{d['avg_steps']:.1f}" if d else "—"
        m_steps = f"{m['avg_steps']:.1f}" if m else "—"
        d_goals = f"{d['avg_goals']:.1f}" if d else "—"
        m_goals = f"{m['avg_goals']:.1f}" if m else "—"
        d_plan  = f"{d['avg_plan_time']:.0f}s" if d else "—"
        m_plan  = f"{m['avg_plan_time']:.0f}s" if m else "—"
        print(f"{label:<15} {d_steps:>12} {m_steps:>12} {d_goals:>12} {m_goals:>12} {d_plan:>12} {m_plan:>12}")
    print("=" * 80)


def main():
    summaries = load_summaries()
    traj_stats = analyze_trajectories()

    print_comparison_table(summaries)
    print_dag_vs_dagmed(summaries)
    print_trajectory_stats(traj_stats)

    # 按 benchmark 看 DAG-Med 的相对收益
    print("\n=== 分析结论 ===")
    medical_benches = ["dsq_med", "gaia_med", "hle_med", "drb2_med"]
    browsecomp_benches = ["bc_en_med", "bc_zh_med"]

    for category, benches, label in [
        ("BrowseComp", browsecomp_benches, "bc_en/bc_zh"),
        ("Medical Research", medical_benches, "dsq/gaia/hle/drb2"),
    ]:
        deltas = []
        for bench_key in benches:
            metric = next(m for k, m, _ in BENCHMARKS if k == bench_key)
            d = get_score(summaries.get(("dag", bench_key)), metric)
            m = get_score(summaries.get(("dag_med", bench_key)), metric)
            if d is not None and m is not None:
                deltas.append((m - d) * 100)
        if deltas:
            print(f"  {category} ({label}): DAG-Med vs DAG avg delta = {sum(deltas)/len(deltas):+.2f}%")


if __name__ == "__main__":
    main()
