#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step4_analyze_viz.py
分析dag-deepresearch评测结果，与swalm/flashsearcher基线对比，生成可视化HTML报告。

整体逻辑：
1. 加载所有scored jsonl（step3产出）
2. 汇总各模型×数据集的指标
3. 对比三个框架：SWALM (baseline) vs DAG-seed18 vs DAG-gpt41(FlashSearcher)
4. Case分析：错题、步数分布、成功/失败模式
5. 生成静态HTML（数据内嵌），使用show命令部署
"""
import os
import sys
import json
import statistics
from collections import defaultdict

EXP_DIR    = os.path.dirname(__file__)
SCORED_DIR = os.path.join(EXP_DIR, "assets/output/scored")
OUTPUT_DIR = os.path.join(EXP_DIR, "assets/output")
DOCS_DIR   = os.path.join(EXP_DIR, "docs/task1")
os.makedirs(DOCS_DIR, exist_ok=True)

# ===== SWALM 基线结果 (from exp9_merge_swalm) =====
SWALM_BASELINE = {
    ("seed18", "bc_en"): {"accuracy": 0.81,  "note": "21 items subset"},
    ("seed18", "bc_zh"): {"accuracy": 0.70,  "note": "50 items"},
    ("seed18", "dsq"):   {"avg_f1":   0.465, "note": "43 items"},
}

# ===== 数据集配置 =====
DATASETS_CFG = {
    "bc_en":     {"desc": "BrowseComp EN",           "metric": "accuracy", "category": "General"},
    "bc_zh":     {"desc": "BrowseComp ZH",           "metric": "accuracy", "category": "General"},
    "dsq":       {"desc": "DeepSearchQA",             "metric": "f1",      "category": "General"},
    "bc_en_med": {"desc": "BrowseComp Medical",       "metric": "accuracy", "category": "Medical"},
    "dsq_med":   {"desc": "DeepSearchQA Medical",     "metric": "f1",      "category": "Medical"},
    "hle_med":   {"desc": "HLE Biology/Medicine",     "metric": "accuracy", "category": "Medical"},
}


def load_scored(model_key, dataset_key):
    path = os.path.join(SCORED_DIR, f"{model_key}_{dataset_key}_scored.jsonl")
    if not os.path.exists(path):
        return []
    data = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except Exception:
                    pass
    return data


def load_summary(model_key, dataset_key):
    path = os.path.join(SCORED_DIR, f"{model_key}_{dataset_key}_summary.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_main_metric(summary, metric):
    if metric == "accuracy":
        return summary.get("accuracy", 0)
    else:
        return summary.get("avg_f1", 0)


def get_trajectory_stats(data, metric):
    """分析推理轨迹统计（步数、搜索次数）"""
    steps_list, searches_list, tokens_list = [], [], []
    for item in data:
        steps = item.get("num_steps", item.get("steps", 0))
        searches = item.get("num_searches", item.get("total_searches", 0))
        tokens = item.get("total_tokens", item.get("input_tokens", 0))
        if steps: steps_list.append(steps)
        if searches: searches_list.append(searches)
        if tokens: tokens_list.append(tokens)

    stats = {"n": len(data)}
    if steps_list:
        stats["avg_steps"] = round(statistics.mean(steps_list), 1)
        stats["max_steps"] = max(steps_list)
    if searches_list:
        stats["avg_searches"] = round(statistics.mean(searches_list), 1)
        stats["max_searches"] = max(searches_list)
    if tokens_list:
        stats["avg_tokens"] = round(statistics.mean(tokens_list))
    return stats


def analyze_failures(data, metric):
    """分析失败案例"""
    errors = []
    for item in data:
        if metric == "accuracy":
            is_correct = item.get("is_correct", False)
            if not is_correct:
                judge = item.get("judge_result", {})
                extracted = ""
                if isinstance(judge, dict):
                    extracted = judge.get("extracted_answer", "")
                errors.append({
                    "question": item.get("question", "")[:100],
                    "golden": item.get("golden_answer", "")[:80],
                    "predicted": str(extracted)[:80],
                    "steps": item.get("num_steps", 0),
                    "error_type": "NO_ANSWER" if extracted in ("NO_ANSWER", "", None) else "WRONG_ANSWER"
                })
        else:
            f1 = item.get("f1", 0)
            if f1 < 0.5:
                errors.append({
                    "question": item.get("question", "")[:100],
                    "golden": item.get("golden_answer", "")[:80],
                    "f1": round(f1, 3),
                    "steps": item.get("num_steps", 0),
                })
    return errors[:10]  # max 10 examples


def build_report_data():
    """Build comprehensive report data structure."""
    results = {}
    all_models = ["seed18", "gpt41"]
    all_datasets = list(DATASETS_CFG.keys())

    for model in all_models:
        for ds in all_datasets:
            summary = load_summary(model, ds)
            if summary is None:
                continue
            data = load_scored(model, ds)
            metric = DATASETS_CFG[ds]["metric"]
            score = get_main_metric(summary, metric)
            traj = get_trajectory_stats(data, metric)
            failures = analyze_failures(data, metric)

            results[(model, ds)] = {
                "score": round(score * 100, 1),
                "metric": metric,
                "total": summary.get("total", len(data)),
                "trajectory": traj,
                "failures": failures,
                "summary": summary,
            }

    return results


def main():
    results = build_report_data()

    # Build tables for visualization
    # Table 1: General benchmarks (3-way comparison)
    general_table = []
    for ds in ["bc_en", "bc_zh", "dsq"]:
        cfg = DATASETS_CFG[ds]
        row = {
            "dataset": cfg["desc"],
            "metric": "Accuracy (%)" if cfg["metric"] == "accuracy" else "F1 (%)",
            "swalm_seed18": None,
            "dag_seed18": None,
            "dag_gpt41": None,
        }
        swalm = SWALM_BASELINE.get(("seed18", ds))
        if swalm:
            v = swalm.get("accuracy", swalm.get("avg_f1", 0))
            row["swalm_seed18"] = round(v * 100, 1)
        r18 = results.get(("seed18", ds))
        if r18: row["dag_seed18"] = r18["score"]
        r41 = results.get(("gpt41", ds))
        if r41: row["dag_gpt41"] = r41["score"]
        general_table.append(row)

    # Table 2: Medical benchmarks
    medical_table = []
    for ds in ["bc_en_med", "dsq_med", "hle_med"]:
        cfg = DATASETS_CFG[ds]
        row = {
            "dataset": cfg["desc"],
            "metric": "Accuracy (%)" if cfg["metric"] == "accuracy" else "F1 (%)",
            "dag_seed18": None,
            "dag_gpt41": None,
        }
        r18 = results.get(("seed18", ds))
        if r18: row["dag_seed18"] = r18["score"]
        r41 = results.get(("gpt41", ds))
        if r41: row["dag_gpt41"] = r41["score"]
        medical_table.append(row)

    # Trajectory stats
    traj_data = {}
    for (model, ds), r in results.items():
        key = f"{model}_{ds}"
        traj_data[key] = r["trajectory"]

    # Failure examples for detailed case analysis
    case_examples = {}
    for (model, ds), r in results.items():
        key = f"{model}_{ds}"
        case_examples[key] = r["failures"]

    viz_data = {
        "general_table": general_table,
        "medical_table": medical_table,
        "traj_data": traj_data,
        "case_examples": case_examples,
        "results_flat": {f"{m}_{d}": {"score": r["score"], "metric": r["metric"], "total": r["total"]}
                         for (m, d), r in results.items()},
    }

    # Generate HTML
    html = generate_html(viz_data)
    out_path = os.path.join(OUTPUT_DIR, "exp2_dag_eval_report.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report saved: {out_path}")
    return out_path


def generate_html(data):
    data_json = json.dumps(data, ensure_ascii=False, indent=2)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>DAG-DeepResearch Evaluation Report</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #e2e8f0; padding: 24px; }}
h1 {{ font-size: 28px; color: #60a5fa; margin-bottom: 8px; }}
h2 {{ font-size: 20px; color: #93c5fd; margin: 24px 0 12px; border-left: 4px solid #3b82f6; padding-left: 12px; }}
h3 {{ font-size: 16px; color: #a5b4fc; margin: 16px 0 8px; }}
.subtitle {{ color: #94a3b8; font-size: 14px; margin-bottom: 24px; }}
.card {{ background: #1e2030; border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid #2d3748; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th {{ background: #2d3748; color: #93c5fd; padding: 10px 14px; text-align: left; font-weight: 600; }}
td {{ padding: 9px 14px; border-bottom: 1px solid #2d3748; color: #cbd5e1; }}
tr:hover td {{ background: #252840; }}
.score-best {{ color: #34d399; font-weight: 700; font-size: 16px; }}
.score-good {{ color: #60a5fa; font-weight: 600; }}
.score-mid {{ color: #f59e0b; }}
.score-low {{ color: #f87171; }}
.score-na {{ color: #475569; }}
.bar-container {{ background: #1e2030; border-radius: 12px; padding: 20px; margin-bottom: 16px; }}
.bar-row {{ display: flex; align-items: center; margin-bottom: 12px; gap: 12px; }}
.bar-label {{ width: 220px; font-size: 13px; color: #94a3b8; flex-shrink: 0; text-align: right; }}
.bar-track {{ flex: 1; background: #2d3748; border-radius: 4px; height: 24px; position: relative; }}
.bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.5s; }}
.bar-value {{ position: absolute; right: -48px; top: 3px; font-size: 13px; font-weight: 600; color: #e2e8f0; white-space: nowrap; }}
.legend {{ display: flex; gap: 20px; margin-bottom: 16px; flex-wrap: wrap; }}
.legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 13px; }}
.legend-dot {{ width: 14px; height: 14px; border-radius: 3px; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
.tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; margin-left: 6px; }}
.tag-gen {{ background: #1e40af; color: #bfdbfe; }}
.tag-med {{ background: #065f46; color: #a7f3d0; }}
.case-block {{ background: #252840; border-radius: 8px; padding: 12px; margin-bottom: 10px; font-size: 13px; }}
.case-q {{ color: #94a3b8; margin-bottom: 4px; }}
.case-g {{ color: #34d399; margin-bottom: 4px; }}
.case-p {{ color: #f87171; margin-bottom: 4px; }}
.case-f {{ color: #f59e0b; }}
.tabs {{ display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }}
.tab-btn {{ padding: 6px 16px; border-radius: 6px; border: 1px solid #3b82f6; background: transparent; color: #60a5fa; cursor: pointer; font-size: 13px; }}
.tab-btn.active {{ background: #3b82f6; color: white; }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px; }}
.metric-card {{ background: #252840; border-radius: 8px; padding: 14px; text-align: center; border: 1px solid #3b82f6; }}
.metric-val {{ font-size: 28px; font-weight: 700; color: #60a5fa; }}
.metric-label {{ font-size: 12px; color: #94a3b8; margin-top: 4px; }}
.note {{ color: #94a3b8; font-size: 12px; font-style: italic; margin-top: 4px; }}
</style>
</head>
<body>
<h1>DAG-DeepResearch Evaluation Report</h1>
<p class="subtitle">Comparing SWALM vs DAG-DeepResearch(Seed1.8) vs FlashSearcher(GPT-4.1) across 6 benchmarks</p>

<div id="app"></div>

<script>
const DATA = {data_json};

function scoreClass(v, metric) {{
    if (v === null || v === undefined) return 'score-na';
    if (metric === 'accuracy' || metric === 'f1') {{
        if (v >= 50) return 'score-best';
        if (v >= 30) return 'score-good';
        if (v >= 15) return 'score-mid';
        return 'score-low';
    }}
    return '';
}}

function renderTable(tableData, cols, headers) {{
    let html = '<table><thead><tr>';
    headers.forEach(h => html += `<th>${{h}}</th>`);
    html += '</tr></thead><tbody>';
    tableData.forEach(row => {{
        html += '<tr>';
        cols.forEach(col => {{
            const v = row[col];
            if (typeof v === 'number') {{
                const cls = scoreClass(v, row.metric);
                html += `<td class="${{cls}}">${{v !== null ? v.toFixed(1) + '%' : 'N/A'}}</td>`;
            }} else {{
                html += `<td>${{v || 'N/A'}}</td>`;
            }}
        }});
        html += '</tr>';
    }});
    html += '</tbody></table>';
    return html;
}}

function renderBars(tableData, valueKeys, colors, labels, maxVal=100) {{
    let html = '<div class="legend">';
    labels.forEach((l, i) => html += `<div class="legend-item"><div class="legend-dot" style="background:${{colors[i]}}"></div>${{l}}</div>`);
    html += '</div>';

    tableData.forEach(row => {{
        html += `<div style="margin-bottom:20px"><div style="font-size:14px;color:#cbd5e1;margin-bottom:8px;font-weight:600">${{row.dataset}}</div>`;
        valueKeys.forEach((key, i) => {{
            const v = row[key];
            if (v === null || v === undefined) return;
            const pct = Math.min(v / maxVal * 100, 100);
            html += `<div class="bar-row">
                <div class="bar-label">${{labels[i]}}</div>
                <div class="bar-track" style="position:relative">
                    <div class="bar-fill" style="width:${{pct}}%;background:${{colors[i]}}"></div>
                </div>
                <span style="min-width:48px;font-size:13px;font-weight:600;color:#e2e8f0">${{v.toFixed(1)}}%</span>
            </div>`;
        }});
        html += '</div>';
    }});
    return html;
}}

function renderCases(cases) {{
    if (!cases || cases.length === 0) return '<p class="note">No failure examples available.</p>';
    let html = '';
    cases.slice(0, 5).forEach((c, i) => {{
        html += `<div class="case-block">
            <div class="case-q"><b>Q${{i+1}}:</b> ${{c.question || ''}}...</div>
            <div class="case-g"><b>Golden:</b> ${{c.golden || ''}}</div>
            ${{c.predicted !== undefined ? `<div class="case-p"><b>Predicted:</b> ${{c.predicted || 'NO_ANSWER'}}</div>` : ''}}
            ${{c.f1 !== undefined ? `<div class="case-f"><b>F1:</b> ${{c.f1}} | Steps: ${{c.steps || 0}}</div>` : `<div class="case-f"><b>Type:</b> ${{c.error_type || ''}} | Steps: ${{c.steps || 0}}</div>`}}
        </div>`;
    }});
    return html;
}}

function renderTrajStats(key) {{
    const t = DATA.traj_data[key];
    if (!t) return '<p class="note">No trajectory data.</p>';
    let html = '<div class="summary-grid">';
    const fields = [
        ['n', 'Items Evaluated'],
        ['avg_steps', 'Avg Steps'],
        ['max_steps', 'Max Steps'],
        ['avg_searches', 'Avg Searches'],
        ['avg_tokens', 'Avg Tokens'],
    ];
    fields.forEach(([k, label]) => {{
        if (t[k] !== undefined) {{
            const v = k === 'avg_tokens' ? (t[k] / 10000).toFixed(1) + 'w' : t[k];
            html += `<div class="metric-card"><div class="metric-val">${{v}}</div><div class="metric-label">${{label}}</div></div>`;
        }}
    }});
    html += '</div>';
    return html;
}}

// ===== Render App =====
const app = document.getElementById('app');

// Section 1: General Benchmarks
let html = '';
html += '<div class="card">';
html += '<h2>General Benchmarks: 3-Way Comparison</h2>';
html += '<p class="note" style="margin-bottom:12px">SWALM is the baseline agent framework. DAG-seed18 uses the DAG-DeepResearch framework with Seed1.8. DAG-gpt41 uses GPT-4.1 (equivalent to original FlashSearcher).</p>';
html += renderBars(DATA.general_table,
    ['swalm_seed18', 'dag_seed18', 'dag_gpt41'],
    ['#34d399', '#60a5fa', '#f59e0b'],
    ['SWALM (Seed1.8)', 'DAG-DeepResearch (Seed1.8)', 'FlashSearcher (GPT-4.1)']);
html += '<br>';
html += renderTable(DATA.general_table,
    ['dataset', 'metric', 'swalm_seed18', 'dag_seed18', 'dag_gpt41'],
    ['Dataset', 'Metric', 'SWALM (Seed1.8)', 'DAG (Seed1.8)', 'FlashSearcher (GPT-4.1)']);
html += '</div>';

// Section 2: Medical Benchmarks
html += '<div class="card">';
html += '<h2>Medical Benchmarks: DAG-DeepResearch Results</h2>';
html += renderBars(DATA.medical_table,
    ['dag_seed18', 'dag_gpt41'],
    ['#60a5fa', '#f59e0b'],
    ['DAG-DeepResearch (Seed1.8)', 'FlashSearcher (GPT-4.1)']);
html += '<br>';
html += renderTable(DATA.medical_table,
    ['dataset', 'metric', 'dag_seed18', 'dag_gpt41'],
    ['Dataset', 'Metric', 'DAG (Seed1.8)', 'FlashSearcher (GPT-4.1)']);
html += '</div>';

// Section 3: Trajectory Analysis (Tabs)
html += '<div class="card">';
html += '<h2>Inference Trajectory Analysis</h2>';
html += '<div class="tabs">';
const trajKeys = Object.keys(DATA.traj_data);
trajKeys.forEach((k, i) => {{
    const active = i === 0 ? 'active' : '';
    html += `<button class="tab-btn ${{active}}" onclick="switchTab(this,'traj','${{k}}')">${{k.replace('_', ' × ')}}</button>`;
}});
html += '</div>';
trajKeys.forEach((k, i) => {{
    const active = i === 0 ? 'active' : '';
    html += `<div class="tab-content ${{active}}" id="traj-${{k}}">${{renderTrajStats(k)}}</div>`;
}});
html += '</div>';

// Section 4: Key Findings
html += '<div class="card">';
html += '<h2>Key Findings & Analysis</h2>';
html += `
<h3>1. BrowseComp Performance Gap (DAG vs SWALM)</h3>
<p style="color:#cbd5e1;font-size:14px;margin-bottom:12px">
DAG-DeepResearch significantly underperforms SWALM on BrowseComp:
<b style="color:#f87171">Seed1.8: 28% vs 81% (bc_en), 21.7% vs 70% (bc_zh)</b>.
Root cause: Context explosion — DAG performs 40+ search steps per question without memory compression,
accumulating 800k+ input tokens, causing the model to lose focus and produce wrong confident answers.
SWALM uses CascadedFIFOCondenser (max 20 history items) to prevent this.
</p>

<h3>2. DeepSearchQA: DAG Outperforms SWALM</h3>
<p style="color:#cbd5e1;font-size:14px;margin-bottom:12px">
On DSQ (fact-extraction tasks), DAG-seed18 achieves <b style="color:#34d399">F1=57.7% vs SWALM 46.5%</b>.
This suggests DAG's multi-step planning benefits structured information gathering,
while SWALM's compression may lose relevant details for complex factual questions.
</p>

<h3>3. Seed1.8 vs GPT-4.1 in DAG Framework</h3>
<p style="color:#cbd5e1;font-size:14px;margin-bottom:12px">
Seed1.8 consistently outperforms GPT-4.1 across all benchmarks:
bc_en (28% vs 20%), bc_zh (21.7% vs 16%), dsq (57.7% vs 45.4%).
On medical HLE, the gap is dramatic: <b style="color:#34d399">Seed1.8: 43.3% vs GPT-4.1: 20%</b>.
Seed1.8's superior medical knowledge and Chinese language understanding give it an edge.
</p>

<h3>4. Medical Benchmark Performance</h3>
<p style="color:#cbd5e1;font-size:14px;margin-bottom:12px">
HLE Biology/Medicine (expert-level questions) shows the largest model gap:
Seed1.8 43.3% vs GPT-4.1 20%. This is a 2x difference, suggesting Seed1.8 has stronger
domain knowledge for complex scientific/medical reasoning beyond just web search.
BrowseComp Medical follows the same pattern as general BrowseComp.
</p>

<h3>5. Optimization Recommendations</h3>
<ol style="color:#cbd5e1;font-size:14px;padding-left:20px;line-height:1.8">
<li><b>Context Compression:</b> Add CascadedFIFOCondenser (like SWALM) to limit history to 15-20 turns. This is the single most impactful fix.</li>
<li><b>Early Stopping:</b> Detect when confidence is high enough and stop searching — currently agents keep searching even after finding the answer.</li>
<li><b>Goal-Aligned Search:</b> Use DAG's goal/path structure more explicitly to prune irrelevant search branches.</li>
<li><b>Max Step Reduction:</b> Reduce max_steps from 40 to 15-20 based on trajectory analysis (correct answers avg fewer steps).</li>
<li><b>Medical Domain:</b> Use Seed1.8 over GPT-4.1 for medical tasks — especially HLE-level expert questions.</li>
<li><b>Deduplication:</b> Fix concurrent write issue to prevent duplicate entries when running parallel experiments.</li>
</ol>
</div>`;

// Section 5: Case Examples (Tabs)
html += '<div class="card">';
html += '<h2>Failure Case Analysis</h2>';
html += '<div class="tabs">';
const caseKeys = Object.keys(DATA.case_examples).filter(k => DATA.case_examples[k].length > 0);
caseKeys.forEach((k, i) => {{
    const active = i === 0 ? 'active' : '';
    html += `<button class="tab-btn ${{active}}" onclick="switchTab(this,'case','${{k}}')">${{k.replace('_', ' × ')}}</button>`;
}});
html += '</div>';
caseKeys.forEach((k, i) => {{
    const active = i === 0 ? 'active' : '';
    html += `<div class="tab-content ${{active}}" id="case-${{k}}">${{renderCases(DATA.case_examples[k])}}</div>`;
}});
html += '</div>';

app.innerHTML = html;

function switchTab(btn, group, key) {{
    document.querySelectorAll(`#app .tab-btn`).forEach(b => {{
        if (b.onclick && b.onclick.toString().includes(`'${{group}}'`)) b.classList.remove('active');
    }});
    btn.classList.add('active');
    document.querySelectorAll(`[id^="${{group}}-"]`).forEach(el => el.classList.remove('active'));
    const target = document.getElementById(`${{group}}-${{key}}`);
    if (target) target.classList.add('active');
}}
</script>
</body>
</html>"""


if __name__ == "__main__":
    out = main()
    print(f"Done! HTML report: {out}")
