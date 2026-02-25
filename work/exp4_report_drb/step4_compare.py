#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 4: 对比分析 + 可视化

整体逻辑:
1. 加载baseline和v2的评分结果(scored JSONL)
2. 对比4维度 + overall的提升/下降
3. 逐条分析：哪些题目提升最多、哪些下降
4. 按语言(zh/en)分组统计
5. 生成HTML可视化报告（静态HTML，数据内嵌）

用法:
  python3 step4_compare.py
  python3 step4_compare.py --baseline assets/output/scored/baseline_race_scored.jsonl --v2 assets/output/scored/v2_race_scored.jsonl
"""

import os
import json
import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "assets" / "output"
SCORED_DIR = OUTPUT_DIR / "scored"

DIMS = ["comprehensiveness", "insight", "instruction_following", "readability", "overall_score"]
DIM_LABELS = {
    "comprehensiveness": "Comprehensiveness",
    "insight": "Insight",
    "instruction_following": "Instruction Following",
    "readability": "Readability",
    "overall_score": "Overall Score",
}


def load_jsonl(path: str) -> list:
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def compute_stats(results: list, dims: list) -> dict:
    """计算各维度的平均分"""
    successful = [r for r in results if "error" not in r]
    if not successful:
        return {}
    stats = {}
    for dim in dims:
        values = [r[dim] for r in successful if dim in r]
        if values:
            stats[dim] = {
                "mean": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "count": len(values),
            }
    return stats


def compare_results(baseline: list, v2: list) -> dict:
    """
    逐条比较baseline和v2的结果:
    1. 按task_id匹配
    2. 计算每条的差异(delta)
    3. 统计整体提升/下降
    """
    b_map = {r["task_id"]: r for r in baseline if "error" not in r}
    v_map = {r["task_id"]: r for r in v2 if "error" not in r}

    common_ids = sorted(set(b_map.keys()) & set(v_map.keys()))

    per_item = []
    for tid in common_ids:
        b = b_map[tid]
        v = v_map[tid]
        item = {
            "task_id": tid,
            "question": b.get("question", "")[:80],
            "language": b.get("language", ""),
        }
        for dim in DIMS:
            b_val = b.get(dim, 0)
            v_val = v.get(dim, 0)
            item[f"{dim}_baseline"] = b_val
            item[f"{dim}_v2"] = v_val
            item[f"{dim}_delta"] = v_val - b_val
        per_item.append(item)

    # 按overall_score delta排序
    per_item.sort(key=lambda x: x.get("overall_score_delta", 0), reverse=True)

    return {
        "common_count": len(common_ids),
        "baseline_only": len(set(b_map.keys()) - set(v_map.keys())),
        "v2_only": len(set(v_map.keys()) - set(b_map.keys())),
        "per_item": per_item,
    }


def generate_html(baseline_stats, v2_stats, comparison, baseline_results, v2_results, output_path):
    """
    生成静态HTML可视化报告:
    - 维度对比柱状图
    - 分语言对比
    - 逐条差异表格
    - 提升/下降Top-10
    """
    # 准备图表数据
    chart_data = []
    for dim in DIMS:
        b_mean = baseline_stats.get(dim, {}).get("mean", 0)
        v_mean = v2_stats.get(dim, {}).get("mean", 0)
        delta = v_mean - b_mean
        chart_data.append({
            "dim": DIM_LABELS.get(dim, dim),
            "dim_key": dim,
            "baseline": round(b_mean, 4),
            "v2": round(v_mean, 4),
            "delta": round(delta, 4),
            "delta_pct": round(delta / b_mean * 100, 1) if b_mean > 0 else 0,
        })

    # 分语言统计
    lang_stats = {}
    for lang in ["zh", "en"]:
        b_lang = [r for r in baseline_results if "error" not in r and r.get("language") == lang]
        v_lang = [r for r in v2_results if "error" not in r and r.get("language") == lang]
        if b_lang and v_lang:
            lang_stats[lang] = {
                "baseline": compute_stats(b_lang, DIMS),
                "v2": compute_stats(v_lang, DIMS),
                "count_baseline": len(b_lang),
                "count_v2": len(v_lang),
            }

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>DRB RACE Evaluation: Baseline vs V2</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f5f7fa; color: #333; padding: 20px; }}
.container {{ max-width: 1400px; margin: 0 auto; }}
h1 {{ text-align: center; margin-bottom: 8px; font-size: 28px; color: #1a1a2e; }}
.subtitle {{ text-align: center; color: #666; margin-bottom: 30px; font-size: 14px; }}
.card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.card h2 {{ margin-bottom: 16px; color: #1a1a2e; font-size: 18px; border-bottom: 2px solid #e8e8e8; padding-bottom: 8px; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 20px; }}
.summary-item {{ background: #f8f9ff; border-radius: 8px; padding: 16px; text-align: center; }}
.summary-item .label {{ font-size: 12px; color: #666; margin-bottom: 4px; }}
.summary-item .value {{ font-size: 24px; font-weight: 700; }}
.summary-item .delta {{ font-size: 13px; margin-top: 4px; }}
.positive {{ color: #22c55e; }}
.negative {{ color: #ef4444; }}
.neutral {{ color: #888; }}
.bar-chart {{ margin: 20px 0; }}
.bar-row {{ display: flex; align-items: center; margin-bottom: 12px; }}
.bar-label {{ width: 180px; font-size: 13px; font-weight: 600; text-align: right; padding-right: 12px; flex-shrink: 0; }}
.bar-container {{ flex: 1; display: flex; gap: 4px; align-items: center; }}
.bar-pair {{ display: flex; flex-direction: column; gap: 3px; flex: 1; }}
.bar-wrapper {{ display: flex; align-items: center; height: 22px; }}
.bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.5s ease; min-width: 2px; }}
.bar-value {{ font-size: 11px; font-weight: 600; margin-left: 6px; white-space: nowrap; }}
.bar-baseline {{ background: linear-gradient(90deg, #94a3b8, #64748b); }}
.bar-v2 {{ background: linear-gradient(90deg, #60a5fa, #3b82f6); }}
.bar-legend {{ display: flex; gap: 20px; justify-content: center; margin-bottom: 12px; font-size: 12px; }}
.bar-legend span {{ display: flex; align-items: center; gap: 6px; }}
.bar-legend .dot {{ width: 12px; height: 12px; border-radius: 3px; }}
.delta-badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }}
.delta-badge.positive {{ background: #dcfce7; color: #166534; }}
.delta-badge.negative {{ background: #fef2f2; color: #991b1b; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th, td {{ padding: 8px 10px; text-align: center; border-bottom: 1px solid #eee; }}
th {{ background: #f1f5f9; font-weight: 600; color: #475569; position: sticky; top: 0; }}
tr:hover {{ background: #f8fafc; }}
.table-wrapper {{ max-height: 600px; overflow-y: auto; }}
.lang-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
.lang-card {{ background: #f8f9ff; border-radius: 8px; padding: 16px; }}
.lang-card h3 {{ margin-bottom: 10px; font-size: 15px; }}
.lang-table {{ width: 100%; font-size: 12px; }}
.lang-table td, .lang-table th {{ padding: 6px 8px; }}
</style>
</head>
<body>
<div class="container">
<h1>DRB RACE Evaluation Comparison</h1>
<p class="subtitle">Baseline (exp3) vs V2 (Optimized Prompts) &middot; {comparison['common_count']} common items evaluated</p>
"""

    # Summary Cards
    html += '<div class="card"><h2>Overall Comparison</h2><div class="summary-grid">'
    for cd in chart_data:
        delta_class = "positive" if cd["delta"] > 0 else ("negative" if cd["delta"] < 0 else "neutral")
        arrow = "+" if cd["delta"] > 0 else ""
        html += f"""<div class="summary-item">
<div class="label">{cd["dim"]}</div>
<div class="value" style="color: #3b82f6;">{cd["v2"]:.4f}</div>
<div class="delta {delta_class}">{arrow}{cd["delta"]:.4f} ({arrow}{cd["delta_pct"]}%)</div>
<div class="label" style="margin-top:4px; font-size:11px;">Baseline: {cd["baseline"]:.4f}</div>
</div>"""
    html += '</div></div>'

    # Bar Chart
    html += """<div class="card"><h2>Dimension Scores Comparison</h2>
<div class="bar-legend">
<span><span class="dot" style="background:#64748b;"></span> Baseline</span>
<span><span class="dot" style="background:#3b82f6;"></span> V2 (Optimized)</span>
</div>
<div class="bar-chart">"""

    for cd in chart_data:
        b_pct = cd["baseline"] * 100
        v_pct = cd["v2"] * 100
        delta_class = "positive" if cd["delta"] > 0 else "negative"
        arrow = "+" if cd["delta"] > 0 else ""
        html += f"""<div class="bar-row">
<div class="bar-label">{cd["dim"]}</div>
<div class="bar-container">
<div class="bar-pair">
<div class="bar-wrapper"><div class="bar-fill bar-baseline" style="width:{b_pct}%"></div><span class="bar-value">{cd["baseline"]:.4f}</span></div>
<div class="bar-wrapper"><div class="bar-fill bar-v2" style="width:{v_pct}%"></div><span class="bar-value">{cd["v2"]:.4f}</span></div>
</div>
<span class="delta-badge {delta_class}">{arrow}{cd["delta"]:.4f}</span>
</div>
</div>"""
    html += '</div></div>'

    # Language Breakdown
    if lang_stats:
        html += '<div class="card"><h2>Breakdown by Language</h2><div class="lang-grid">'
        lang_names = {"zh": "Chinese", "en": "English"}
        for lang, ls in lang_stats.items():
            html += f'<div class="lang-card"><h3>{lang_names.get(lang, lang)} (Baseline: {ls["count_baseline"]}, V2: {ls["count_v2"]})</h3>'
            html += '<table class="lang-table"><tr><th>Dimension</th><th>Baseline</th><th>V2</th><th>Delta</th></tr>'
            for dim in DIMS:
                b_val = ls["baseline"].get(dim, {}).get("mean", 0)
                v_val = ls["v2"].get(dim, {}).get("mean", 0)
                delta = v_val - b_val
                delta_class = "positive" if delta > 0 else ("negative" if delta < 0 else "neutral")
                arrow = "+" if delta > 0 else ""
                html += f'<tr><td style="text-align:left;">{DIM_LABELS.get(dim, dim)}</td><td>{b_val:.4f}</td><td>{v_val:.4f}</td><td class="{delta_class}">{arrow}{delta:.4f}</td></tr>'
            html += '</table></div>'
        html += '</div></div>'

    # Per-item Table
    per_item = comparison["per_item"]
    html += '<div class="card"><h2>Per-Item Comparison (sorted by Overall Score delta)</h2>'
    html += '<div class="table-wrapper"><table>'
    html += '<tr><th>#</th><th>Task ID</th><th>Lang</th><th>Question</th>'
    for dim in DIMS:
        html += f'<th>{DIM_LABELS.get(dim, dim)[:8]}<br/>B / V2 / &Delta;</th>'
    html += '</tr>'

    for i, item in enumerate(per_item):
        html += f'<tr><td>{i+1}</td><td>{item["task_id"]}</td><td>{item["language"]}</td><td style="text-align:left;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{item["question"]}">{item["question"]}</td>'
        for dim in DIMS:
            b = item.get(f"{dim}_baseline", 0)
            v = item.get(f"{dim}_v2", 0)
            d = item.get(f"{dim}_delta", 0)
            delta_class = "positive" if d > 0.01 else ("negative" if d < -0.01 else "neutral")
            arrow = "+" if d > 0 else ""
            html += f'<td><span style="color:#64748b;">{b:.3f}</span> / <span style="color:#3b82f6;">{v:.3f}</span> / <span class="{delta_class}">{arrow}{d:.3f}</span></td>'
        html += '</tr>'

    html += '</table></div></div>'

    # Top improvers and decliners
    top_n = min(10, len(per_item))
    if top_n > 0:
        html += '<div class="card"><h2>Top Improvements & Declines</h2><div class="lang-grid">'

        # Top improvers
        html += '<div class="lang-card"><h3 class="positive">Top Improvements</h3><table class="lang-table">'
        html += '<tr><th>Task ID</th><th>Question</th><th>Overall Delta</th></tr>'
        for item in per_item[:top_n]:
            d = item.get("overall_score_delta", 0)
            if d <= 0:
                break
            html += f'<tr><td>{item["task_id"]}</td><td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{item["question"]}">{item["question"]}</td><td class="positive">+{d:.4f}</td></tr>'
        html += '</table></div>'

        # Top decliners
        html += '<div class="lang-card"><h3 class="negative">Top Declines</h3><table class="lang-table">'
        html += '<tr><th>Task ID</th><th>Question</th><th>Overall Delta</th></tr>'
        for item in reversed(per_item[-top_n:]):
            d = item.get("overall_score_delta", 0)
            if d >= 0:
                break
            html += f'<tr><td>{item["task_id"]}</td><td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{item["question"]}">{item["question"]}</td><td class="negative">{d:.4f}</td></tr>'
        html += '</table></div>'
        html += '</div></div>'

    html += '</div></body></html>'

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"HTML report saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Step 4: Compare Baseline vs V2")
    parser.add_argument("--baseline", type=str, default=None, help="Baseline scored JSONL")
    parser.add_argument("--v2", type=str, default=None, help="V2 scored JSONL")
    parser.add_argument("--output", type=str, default=None, help="Output HTML path")
    args = parser.parse_args()

    baseline_path = args.baseline or str(SCORED_DIR / "baseline_race_scored.jsonl")
    v2_path = args.v2 or str(SCORED_DIR / "v2_race_scored.jsonl")
    output_html = args.output or str(OUTPUT_DIR / "comparison_report.html")

    if not os.path.exists(baseline_path):
        logger.error(f"Baseline file not found: {baseline_path}")
        return
    if not os.path.exists(v2_path):
        logger.error(f"V2 file not found: {v2_path}")
        return

    baseline_results = load_jsonl(baseline_path)
    v2_results = load_jsonl(v2_path)
    logger.info(f"Loaded baseline: {len(baseline_results)}, v2: {len(v2_results)}")

    baseline_stats = compute_stats(baseline_results, DIMS)
    v2_stats = compute_stats(v2_results, DIMS)

    comparison = compare_results(baseline_results, v2_results)
    logger.info(f"Common items: {comparison['common_count']}")

    # Print comparison
    print(f"\n{'='*70}")
    print(f"{'Dimension':<25} {'Baseline':>10} {'V2':>10} {'Delta':>10} {'%':>8}")
    print(f"{'-'*70}")
    for dim in DIMS:
        b = baseline_stats.get(dim, {}).get("mean", 0)
        v = v2_stats.get(dim, {}).get("mean", 0)
        d = v - b
        pct = d / b * 100 if b > 0 else 0
        arrow = "+" if d > 0 else ""
        print(f"  {DIM_LABELS.get(dim, dim):<23} {b:>10.4f} {v:>10.4f} {arrow}{d:>9.4f} {arrow}{pct:>7.1f}%")
    print(f"{'='*70}")

    # Generate HTML
    generate_html(baseline_stats, v2_stats, comparison, baseline_results, v2_results, output_html)
    print(f"\nHTML report: {output_html}")


if __name__ == "__main__":
    main()
