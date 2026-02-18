#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step5_viz.py
生成对比表格 HTML：行=框架，列=benchmark，展示各框架在8个医学 benchmark 上的性能。

整体逻辑：
1. 加载 assets/output/scored/ 下的所有 summary.json 文件
2. 构建对比数据矩阵（框架 × benchmark）
3. 生成静态 HTML，数据内嵌（无服务器依赖），包含：
   - 汇总表格（行=框架，列=benchmark）
   - 柱状图对比（每个 benchmark 三个框架的得分）
4. 使用 show 命令部署到 viz 目录

用法：
  python3 step5_viz.py
  show exp3_med_full.html exp3_med_full  # 部署
"""
import os
import json
import subprocess

EXP_DIR    = os.path.dirname(__file__)
SCORED_DIR = os.path.join(EXP_DIR, "assets/output/scored")
OUTPUT_HTML = os.path.join(EXP_DIR, "assets/output/exp3_med_full.html")

FRAMEWORKS = [
    ("swalm",        "SWALM+Seed16"),
    ("flashsearcher", "FlashSearcher+Seed16"),
    ("dag",           "DAG+Seed16"),
    ("dag_med",       "DAG-Med+Seed16"),
]

BENCHMARKS_ORDER = [
    "bc_en_med", "bc_zh_med", "dsq_med", "drb_med",
    "gaia_med", "hle_med", "drb2_med", "xbench_med"
]

BENCH_LABELS = {
    "bc_en_med":  "BC-EN-Med",
    "bc_zh_med":  "BC-ZH-Med",
    "dsq_med":    "DSQ-Med",
    "drb_med":    "DRB-Med",
    "gaia_med":   "GAIA-Med",
    "hle_med":    "HLE-Med",
    "drb2_med":   "DRB2-Med",
    "xbench_med": "XBench-Med",
}

BENCH_METRICS = {
    "bc_en_med":  "accuracy",
    "bc_zh_med":  "accuracy",
    "dsq_med":    "f1",
    "drb_med":    "accuracy",
    "gaia_med":   "accuracy",
    "hle_med":    "accuracy",
    "drb2_med":   "rubric",
    "xbench_med": "accuracy",
}


def load_summaries():
    """加载所有 summary.json 文件，返回 (framework, bench_key) -> summary 字典"""
    summaries = {}
    if not os.path.exists(SCORED_DIR):
        return summaries
    for fname in os.listdir(SCORED_DIR):
        if not fname.endswith("_summary.json"):
            continue
        # 格式: {framework}_{bench_key}_summary.json
        # bench_key 包含 _med，需要小心切割
        stem = fname.replace("_summary.json", "")
        # 找到 framework（第一个 _）
        for fw_key, _ in FRAMEWORKS:
            if stem.startswith(fw_key + "_"):
                bench_key = stem[len(fw_key) + 1:]
                path = os.path.join(SCORED_DIR, fname)
                with open(path) as f:
                    summaries[(fw_key, bench_key)] = json.load(f)
                break
    return summaries


def get_score(summary, bench_key):
    """从 summary 中提取主要指标值（0~1 之间）"""
    if not summary:
        return None
    metric = BENCH_METRICS.get(bench_key, "accuracy")
    if metric == "f1":
        return summary.get("avg_f1")
    elif metric == "rubric":
        return summary.get("avg_pass_rate")
    else:
        return summary.get("accuracy")


def build_table_data(summaries):
    """构建表格数据"""
    rows = []
    for fw_key, fw_label in FRAMEWORKS:
        row = {"framework": fw_label, "scores": {}}
        for bench in BENCHMARKS_ORDER:
            summary = summaries.get((fw_key, bench))
            score   = get_score(summary, bench)
            total   = summary.get("total", 0) if summary else 0
            row["scores"][bench] = {
                "score": round(score * 100, 1) if score is not None else None,
                "total": total,
                "raw":   summary,
            }
        rows.append(row)
    return rows


def generate_html(table_data, summaries):
    bench_labels_json   = json.dumps({b: BENCH_LABELS[b] for b in BENCHMARKS_ORDER}, ensure_ascii=False)
    table_data_json     = json.dumps(table_data, ensure_ascii=False)
    benchmarks_json     = json.dumps(BENCHMARKS_ORDER, ensure_ascii=False)
    benchmarks_metrics_json = json.dumps(BENCH_METRICS, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Medical Benchmark Evaluation: exp3_med_full</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #0f1117;
    color: #e0e0e0;
    min-height: 100vh;
    padding: 24px;
  }}
  h1 {{ font-size: 1.8rem; color: #fff; margin-bottom: 8px; }}
  .subtitle {{ color: #888; font-size: 0.9rem; margin-bottom: 32px; }}
  h2 {{ font-size: 1.2rem; color: #ccc; margin-bottom: 16px; margin-top: 32px; }}

  /* Summary Table */
  .table-wrap {{ overflow-x: auto; margin-bottom: 40px; }}
  table {{ border-collapse: collapse; width: 100%; min-width: 900px; }}
  th, td {{
    padding: 10px 14px;
    text-align: center;
    border: 1px solid #2a2a3a;
    font-size: 0.85rem;
  }}
  th {{ background: #1a1a2e; color: #a0a0c0; font-weight: 600; }}
  td:first-child {{ text-align: left; font-weight: 600; color: #c0c0e0; }}
  tr:nth-child(odd) td {{ background: #141422; }}
  tr:nth-child(even) td {{ background: #181828; }}
  .score-cell {{ font-size: 1rem; font-weight: 700; }}
  .score-na {{ color: #555; }}
  .score-best {{ color: #4caf50; }}
  .score-mid  {{ color: #ff9800; }}
  .score-low  {{ color: #f44336; }}

  /* Bar Charts */
  .charts-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 20px;
  }}
  .chart-card {{
    background: #141422;
    border: 1px solid #2a2a3a;
    border-radius: 8px;
    padding: 16px;
  }}
  .chart-title {{ font-size: 0.95rem; color: #bbb; margin-bottom: 12px; font-weight: 600; }}
  .bar-group {{ margin-bottom: 10px; }}
  .bar-label {{ font-size: 0.75rem; color: #999; margin-bottom: 4px; }}
  .bar-row {{ display: flex; align-items: center; gap: 8px; }}
  .bar-track {{ flex: 1; background: #222; border-radius: 4px; height: 20px; overflow: visible; position: relative; }}
  .bar-fill {{
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s ease;
  }}
  .bar-value {{ font-size: 0.8rem; color: #ccc; white-space: nowrap; min-width: 50px; }}

  .fw-0 {{ background: linear-gradient(90deg, #7c4dff, #b39ddb); }}
  .fw-1 {{ background: linear-gradient(90deg, #00897b, #80cbc4); }}
  .fw-2 {{ background: linear-gradient(90deg, #e64a19, #ffccbc); }}

  .legend {{
    display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 0.85rem; color: #bbb; }}
  .legend-color {{ width: 14px; height: 14px; border-radius: 3px; }}

  .metric-tag {{
    display: inline-block;
    background: #1e1e30;
    color: #7986cb;
    font-size: 0.7rem;
    padding: 2px 6px;
    border-radius: 4px;
    margin-left: 6px;
    vertical-align: middle;
  }}
</style>
</head>
<body>
<h1>Medical Benchmark Evaluation — exp3_med_full</h1>
<p class="subtitle">
  Model: Seed1.6 (ep-20250724221742-fddgp) &nbsp;|&nbsp;
  Frameworks: SWALM, FlashSearcher (no planning), DAG (with planning) &nbsp;|&nbsp;
  8 Medical Benchmarks &times; 3 Frameworks
</p>

<h2>Performance Summary Table</h2>
<div class="table-wrap" id="summary-table"></div>

<h2>Per-Benchmark Bar Charts</h2>
<div class="legend" id="legend"></div>
<div class="charts-grid" id="charts"></div>

<script>
const BENCHMARKS = {benchmarks_json};
const BENCH_LABELS = {bench_labels_json};
const TABLE_DATA = {table_data_json};

const FW_COLORS = ['fw-0', 'fw-1', 'fw-2'];
const FW_SOLID  = ['#9575cd', '#26a69a', '#ef6c00'];

// ---- Legend ----
const legendEl = document.getElementById('legend');
TABLE_DATA.forEach((row, i) => {{
  const item = document.createElement('div');
  item.className = 'legend-item';
  item.innerHTML = `<div class="legend-color" style="background:${{FW_SOLID[i]}}"></div>${{row.framework}}`;
  legendEl.appendChild(item);
}});

// ---- Summary Table ----
function getColorClass(score, colScores) {{
  if (score === null) return 'score-na';
  const valid = colScores.filter(s => s !== null);
  const maxS  = Math.max(...valid);
  if (score === maxS)        return 'score-best';
  if (score >= maxS - 10)    return 'score-mid';
  return 'score-low';
}}

const tableEl = document.getElementById('summary-table');
let html = '<table><thead><tr><th>Framework</th>';
const BENCH_METRIC_MAP = {benchmarks_metrics_json};
BENCHMARKS.forEach(b => {{
  const m = BENCH_METRIC_MAP[b] || 'accuracy';
  const metricTag = m === 'f1' ? '<span class="metric-tag">F1</span>'
                  : m === 'rubric' ? '<span class="metric-tag">Rubric</span>'
                  : '<span class="metric-tag">ACC</span>';
  html += `<th>${{BENCH_LABELS[b]}}${{metricTag}}</th>`;
}});
html += '<th>Average</th></tr></thead><tbody>';

TABLE_DATA.forEach((row, i) => {{
  const colScores = BENCHMARKS.map(b => row.scores[b].score);
  const validScores = colScores.filter(s => s !== null);
  const avg = validScores.length ? (validScores.reduce((a,b)=>a+b,0)/validScores.length).toFixed(1) : '-';

  html += `<tr><td>${{row.framework}}</td>`;
  BENCHMARKS.forEach((b, j) => {{
    const s = row.scores[b];
    const allColScores = TABLE_DATA.map(r => r.scores[b].score);
    if (s.score === null) {{
      html += `<td class="score-cell score-na">-</td>`;
    }} else {{
      const cls = getColorClass(s.score, allColScores);
      html += `<td class="score-cell ${{cls}}">${{s.score}}%<br><small style="color:#666;font-weight:400">n=${{s.total}}</small></td>`;
    }}
  }});
  html += `<td class="score-cell" style="color:#90caf9">${{avg}}%</td></tr>`;
}});
html += '</tbody></table>';
tableEl.innerHTML = html;

// ---- Bar Charts ----
const chartsEl = document.getElementById('charts');
BENCHMARKS.forEach(bench => {{
  const card = document.createElement('div');
  card.className = 'chart-card';
  const m2 = BENCH_METRIC_MAP[bench] || 'accuracy';
  const metricLabel = m2 === 'f1' ? 'F1 Score' : m2 === 'rubric' ? 'Rubric Pass Rate' : 'Accuracy';
  card.innerHTML = `<div class="chart-title">${{BENCH_LABELS[bench]}} <span style="color:#666;font-size:0.75rem">(${{metricLabel}})</span></div>`;

  TABLE_DATA.forEach((row, i) => {{
    const s = row.scores[bench];
    const score = s.score;
    const barWidth = score !== null ? score : 0;
    const label = score !== null ? score + '%' : 'N/A';

    const group = document.createElement('div');
    group.className = 'bar-group';
    group.innerHTML = `
      <div class="bar-label">${{row.framework}}</div>
      <div class="bar-row">
        <div class="bar-track">
          <div class="bar-fill ${{FW_COLORS[i]}}" style="width: ${{barWidth}}%"></div>
        </div>
        <div class="bar-value">${{label}}</div>
      </div>`;
    card.appendChild(group);
  }});
  chartsEl.appendChild(card);
}});
</script>
</body>
</html>"""
    return html


def main():
    summaries  = load_summaries()
    table_data = build_table_data(summaries)

    print("\n===== 数据汇总 =====")
    for fw_key, fw_label in FRAMEWORKS:
        scores = []
        for bench in BENCHMARKS_ORDER:
            s = summaries.get((fw_key, bench))
            sc = get_score(s, bench)
            scores.append(f"{bench}={round(sc*100,1) if sc else 'N/A'}%")
        print(f"{fw_label}: {', '.join(scores)}")

    html = generate_html(table_data, summaries)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML 已生成: {OUTPUT_HTML}")

    # 尝试使用 show 命令部署
    try:
        result = subprocess.run(
            ["bash", "-c", f"source ~/.zshrc 2>/dev/null; show {OUTPUT_HTML} exp3_med_full"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print("show 命令成功:", result.stdout.strip())
        else:
            print(f"show 命令输出: {result.stdout.strip()}")
            print(f"show 命令错误: {result.stderr.strip()}")
    except Exception as e:
        print(f"[INFO] show 命令未执行，请手动运行: show {OUTPUT_HTML} exp3_med_full")


if __name__ == "__main__":
    main()
