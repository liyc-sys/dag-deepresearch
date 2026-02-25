#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成exp4_report_drb对接工作可视化HTML（带Tab切换）。

Tab 1: Overview — 状态/进度/对齐分析/baseline分数/v2对比/质量对比
Tab 2: Case Analysis — 高分低分case剖析 + 统计洞察 + 维度分析
Tab 3: Detail — baseline逐条明细 + v2已完成明细 + 后续步骤
"""

import json, re, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def read_jsonl(path):
    data = []
    with open(path) as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

# ===== 读取数据 =====
baseline_scored = read_jsonl(os.path.join(BASE_DIR, 'assets/output/scored/baseline_race_scored.jsonl'))
v2_test_scored = read_jsonl(os.path.join(BASE_DIR, 'assets/output/scored/v2_test_race_scored.jsonl'))
v2_reports = read_jsonl(os.path.join(BASE_DIR, 'assets/output/report_v2_drb_med.jsonl'))
exp3_reports = read_jsonl(os.path.join(BASE_DIR, 'assets/input/exp3_report_drb_med_med.jsonl'))
refs = read_jsonl(os.path.join(BASE_DIR, 'assets/input/reference.jsonl'))

exp3_map = {r.get('task_id',''): r for r in exp3_reports}
ref_map = {r.get('prompt',''): r for r in refs}

dims = ["comprehensiveness", "insight", "instruction_following", "readability", "overall_score"]
dim_labels = {
    "comprehensiveness": "Comprehensiveness",
    "insight": "Insight",
    "instruction_following": "Instruction Following",
    "readability": "Readability",
    "overall_score": "Overall Score",
}

# ===== 统计计算 =====
baseline_avgs = {}
for d in dims:
    vals = [r[d] for r in baseline_scored if d in r and "error" not in r]
    baseline_avgs[d] = sum(vals)/len(vals) if vals else 0

lang_stats = {}
for lang in ["zh", "en"]:
    items = [r for r in baseline_scored if r.get("language") == lang and "error" not in r]
    if items:
        lang_stats[lang] = {}
        for d in dims:
            vals = [r[d] for r in items if d in r]
            lang_stats[lang][d] = sum(vals)/len(vals) if vals else 0
        lang_stats[lang]["count"] = len(items)

v2_test_avgs = {}
for d in dims:
    vals = [r[d] for r in v2_test_scored if d in r and "error" not in r]
    v2_test_avgs[d] = sum(vals)/len(vals) if vals else 0

exp3_lens = [len(r.get("report", "")) for r in exp3_reports]
v2_lens = [len(r.get("report", "")) for r in v2_reports]
exp3_avg_len = sum(exp3_lens)/len(exp3_lens) if exp3_lens else 0
v2_avg_len = sum(v2_lens)/len(v2_lens) if v2_lens else 0
v2_avg_time = sum(r.get("total_time", 0) for r in v2_reports) / len(v2_reports) if v2_reports else 0

n_v2 = len(v2_reports)

# ===== Case 分析数据 =====
baseline_sorted = sorted([r for r in baseline_scored if "error" not in r], key=lambda x: x.get('overall_score', 0), reverse=True)
top5 = baseline_sorted[:5]
bot5 = baseline_sorted[-5:]

def get_case_features(r):
    """提取单个case的详细特征"""
    e = exp3_map.get(r['task_id'], {})
    report = e.get('report', '')
    ref_art = ref_map.get(r['question'], {}).get('article', '')
    sections = [l.strip() for l in report.split('\n') if l.strip().startswith('#')]
    urls = re.findall(r'https?://[^\s\)\]]+', report)
    cn_chars = sum(1 for c in report if '\u4e00' <= c <= '\u9fff')
    cn_ratio = cn_chars / max(len(report), 1)
    lang_mismatch = r['language'] == 'zh' and cn_ratio < 0.15
    tables = report.count('|---')
    return {
        'task_id': r['task_id'],
        'question': r['question'],
        'language': r['language'],
        'overall': r.get('overall_score', 0),
        'comp': r.get('comprehensiveness', 0),
        'insight': r.get('insight', 0),
        'instr': r.get('instruction_following', 0),
        'read': r.get('readability', 0),
        'report_len': len(report),
        'ref_len': len(ref_art),
        'len_ratio': len(report) / max(len(ref_art), 1),
        'sections': len(sections),
        'section_titles': sections[:8],
        'urls': len(urls),
        'tables': tables,
        'cn_ratio': cn_ratio,
        'lang_mismatch': lang_mismatch,
        'raw_target': r.get('raw_target_total', 0),
        'raw_ref': r.get('raw_reference_total', 0),
        'report_first_300': report[:300],
    }

top5_features = [get_case_features(r) for r in top5]
bot5_features = [get_case_features(r) for r in bot5]

# 全量特征（用于统计）
all_features = [get_case_features(r) for r in baseline_sorted]

# 相关性计算
def corr(xs, ys):
    n = len(xs)
    mx, my = sum(xs)/n, sum(ys)/n
    cov = sum((x-mx)*(y-my) for x, y in zip(xs, ys)) / n
    sx = (sum((x-mx)**2 for x in xs)/n)**0.5
    sy = (sum((y-my)**2 for y in ys)/n)**0.5
    return cov / (sx * sy) if sx > 0 and sy > 0 else 0

overalls = [f['overall'] for f in all_features]
corr_data = {}
for feat in ['report_len', 'ref_len', 'len_ratio', 'urls', 'raw_target', 'raw_ref']:
    vals = [f[feat] for f in all_features]
    corr_data[feat] = corr(overalls, vals)

# 维度分析
dim_analysis = {}
for d in ['comprehensiveness', 'insight', 'instruction_following', 'readability']:
    vals = [r[d] for r in baseline_scored if d in r and 'error' not in r]
    above_05 = sum(1 for v in vals if v >= 0.5)
    dim_analysis[d] = {
        'mean': sum(vals)/len(vals),
        'min': min(vals),
        'max': max(vals),
        'above_05': above_05,
        'total': len(vals),
    }

# V2 details
v2_details = []
for r in v2_reports:
    v2_details.append({
        "task_id": r.get("task_id", ""),
        "question": r.get("question", "")[:80],
        "report_len": len(r.get("report", "")),
        "total_time": r.get("total_time", 0),
        "input_tokens": r.get("input_tokens", 0),
        "output_tokens": r.get("output_tokens", 0),
    })

# baseline items for detail tab
baseline_items = []
for r in baseline_sorted:
    baseline_items.append({
        "task_id": r.get("task_id", ""),
        "question": r.get("question", "")[:60],
        "language": r.get("language", ""),
        "overall_score": r.get("overall_score", 0),
        "comprehensiveness": r.get("comprehensiveness", 0),
        "insight": r.get("insight", 0),
        "instruction_following": r.get("instruction_following", 0),
        "readability": r.get("readability", 0),
    })

# ===== HTML 生成 =====

# CSS
css = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; padding: 0; line-height: 1.6; }
.header { text-align: center; padding: 20px 20px 0; }
.header h1 { font-size: 24px; color: #f1f5f9; }
.header .subtitle { color: #94a3b8; font-size: 13px; margin-top: 4px; }

/* Tabs */
.tab-bar { display: flex; gap: 0; margin: 16px 20px 0; border-bottom: 2px solid #334155; }
.tab-btn { padding: 10px 24px; background: transparent; color: #94a3b8; border: none; font-size: 14px; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.2s; }
.tab-btn:hover { color: #e2e8f0; }
.tab-btn.active { color: #60a5fa; border-bottom-color: #3b82f6; }
.tab-content { display: none; padding: 16px 20px 20px; max-width: 1400px; margin: 0 auto; }
.tab-content.active { display: block; }

/* Cards */
.card { background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 16px; border: 1px solid #334155; }
.card h2 { font-size: 16px; color: #f8fafc; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #334155; }
.badge { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 10px; margin-left: 8px; font-weight: 500; }
.badge-done { background: #166534; color: #86efac; }
.badge-running { background: #854d0e; color: #fde68a; }
.badge-pending { background: #1e3a5f; color: #93c5fd; }
.up { color: #4ade80; }
.down { color: #f87171; }
.muted { color: #64748b; }

/* Grids */
.status-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.status-item { background: #0f172a; border-radius: 8px; padding: 14px; text-align: center; border: 1px solid #334155; }
.status-item .label { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }
.status-item .value { font-size: 28px; font-weight: 700; margin: 4px 0; }
.status-item .sub { font-size: 11px; color: #64748b; }
.score-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }
.score-card { background: #0f172a; border-radius: 8px; padding: 14px; text-align: center; border: 1px solid #334155; }
.score-card .dim { font-size: 11px; color: #94a3b8; margin-bottom: 4px; }
.score-card .val { font-size: 22px; font-weight: 700; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } }

/* Progress */
.progress-container { background: #0f172a; border-radius: 8px; padding: 16px; border: 1px solid #334155; }
.progress-bar { width: 100%; height: 24px; background: #1e293b; border-radius: 12px; overflow: hidden; position: relative; }
.progress-fill { height: 100%; border-radius: 12px; background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.progress-text { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 12px; font-weight: 600; color: white; }

/* Bars */
.bar-section { margin: 16px 0; }
.bar-row { display: flex; align-items: center; margin-bottom: 10px; }
.bar-label { width: 160px; font-size: 12px; color: #94a3b8; text-align: right; padding-right: 12px; flex-shrink: 0; }
.bar-track { flex: 1; height: 36px; position: relative; background: #0f172a; border-radius: 6px; overflow: hidden; border: 1px solid #334155; }
.bar-fill-top { position: absolute; top: 0; left: 0; height: 50%; }
.bar-fill-bot { position: absolute; bottom: 0; left: 0; height: 50%; }
.bar-val { position: absolute; right: -70px; font-size: 10px; font-weight: 600; width: 60px; text-align: left; }
.bar-mid { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: #475569; z-index: 2; }
.legend { display: flex; gap: 20px; justify-content: center; margin: 8px 0 12px; font-size: 12px; }
.legend-item { display: flex; align-items: center; gap: 6px; color: #94a3b8; }
.legend-dot { width: 12px; height: 6px; border-radius: 2px; }

/* Tables */
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { background: #0f172a; color: #94a3b8; font-weight: 600; padding: 8px; text-align: center; border-bottom: 2px solid #334155; position: sticky; top: 0; z-index: 1; }
td { padding: 7px 8px; text-align: center; border-bottom: 1px solid #1e293b; }
tr:hover td { background: #1e293b; }
.table-scroll { max-height: 500px; overflow-y: auto; border-radius: 8px; border: 1px solid #334155; }

/* Alignment */
.align-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.align-card { background: #0f172a; border-radius: 8px; padding: 16px; border: 1px solid #334155; }
.align-card h3 { font-size: 14px; margin-bottom: 10px; }
.align-item { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 6px; font-size: 12px; }
.align-icon { flex-shrink: 0; width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; }
.align-ok { background: #166534; color: #86efac; }
.diff-table { width: 100%; font-size: 11px; }
.diff-table td { padding: 5px 6px; border-bottom: 1px solid #334155; vertical-align: top; }
.diff-table .diff-label { color: #94a3b8; font-weight: 600; width: 120px; }
.diff-impact { display: inline-block; padding: 1px 6px; border-radius: 8px; font-size: 10px; font-weight: 600; }
.impact-high { background: #7f1d1d; color: #fca5a5; }
.impact-mid { background: #78350f; color: #fde68a; }
.impact-low { background: #1e3a5f; color: #93c5fd; }

/* Case Analysis */
.case-card { background: #0f172a; border-radius: 10px; padding: 16px; margin-bottom: 12px; border: 1px solid #334155; }
.case-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.case-header .case-id { font-size: 14px; font-weight: 700; }
.case-header .case-score { font-size: 20px; font-weight: 700; }
.case-question { font-size: 12px; color: #cbd5e1; margin-bottom: 10px; line-height: 1.5; }
.case-dims { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 10px; }
.case-dim { background: #1e293b; border-radius: 6px; padding: 8px; text-align: center; }
.case-dim .dim-label { font-size: 10px; color: #64748b; }
.case-dim .dim-val { font-size: 16px; font-weight: 700; }
.case-meta { display: grid; grid-template-columns: repeat(3, 1fr) 2fr; gap: 8px; font-size: 11px; }
.case-meta-item { background: #1e293b; border-radius: 6px; padding: 6px 8px; }
.case-meta-item .meta-label { color: #64748b; font-size: 10px; }
.case-meta-item .meta-val { color: #e2e8f0; font-weight: 600; }
.case-sections { margin-top: 8px; font-size: 11px; color: #94a3b8; }
.case-sections .sec-title { padding: 2px 0; border-left: 2px solid #334155; padding-left: 8px; margin-bottom: 2px; }
.insight-box { background: #172554; border: 1px solid #1e40af; border-radius: 8px; padding: 14px; margin-bottom: 12px; }
.insight-box h3 { font-size: 14px; color: #93c5fd; margin-bottom: 8px; }
.insight-box p { font-size: 12px; color: #bfdbfe; line-height: 1.6; }
.insight-box ul { font-size: 12px; color: #bfdbfe; padding-left: 20px; }
.insight-box li { margin-bottom: 4px; }

/* Correlation bar */
.corr-row { display: flex; align-items: center; margin-bottom: 8px; }
.corr-label { width: 140px; font-size: 12px; color: #94a3b8; text-align: right; padding-right: 10px; }
.corr-bar-container { flex: 1; height: 20px; position: relative; }
.corr-bar-bg { position: absolute; top: 0; left: 0; right: 0; height: 100%; background: #1e293b; border-radius: 4px; }
.corr-bar-center { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: #475569; z-index: 2; }
.corr-bar-fill { position: absolute; top: 2px; bottom: 2px; border-radius: 3px; z-index: 1; }
.corr-val { margin-left: 8px; font-size: 11px; font-weight: 600; width: 60px; }

/* Next steps */
.step-list { list-style: none; }
.step-list li { padding: 8px 12px; margin-bottom: 6px; background: #0f172a; border-radius: 6px; border-left: 3px solid #3b82f6; font-size: 13px; }
.step-list li code { background: #334155; padding: 2px 6px; border-radius: 3px; font-size: 11px; color: #93c5fd; }

/* Dim analysis bar */
.dim-bar-row { display: flex; align-items: center; margin-bottom: 8px; }
.dim-bar-label { width: 170px; font-size: 12px; color: #94a3b8; text-align: right; padding-right: 10px; }
.dim-bar-track { flex: 1; height: 24px; background: #1e293b; border-radius: 6px; position: relative; overflow: visible; border: 1px solid #334155; }
.dim-bar-fill { height: 100%; border-radius: 5px; position: relative; }
.dim-bar-mid { position: absolute; left: 50%; top: -2px; bottom: -2px; width: 2px; background: #fbbf24; z-index: 3; }
.dim-bar-stats { margin-left: 10px; font-size: 11px; color: #94a3b8; width: 120px; }
"""

def color_val(v):
    if v >= 0.5: return f'<span style="color:#4ade80; font-weight:600;">{v:.4f}</span>'
    elif v >= 0.45: return f'<span style="color:#fbbf24;">{v:.4f}</span>'
    else: return f'<span style="color:#f87171;">{v:.4f}</span>'

def case_color(v):
    if v >= 0.5: return "#4ade80"
    elif v >= 0.45: return "#fbbf24"
    else: return "#f87171"

def render_case_card(feat, rank_label):
    """渲染单个case的详细卡片"""
    oc = case_color(feat['overall'])
    mismatch_tag = '<span style="background:#7f1d1d; color:#fca5a5; padding:1px 6px; border-radius:8px; font-size:10px; font-weight:600; margin-left:6px;">LANG MISMATCH</span>' if feat['lang_mismatch'] else ''

    h = f'''<div class="case-card">
<div class="case-header">
<div><span class="case-id">{rank_label} &middot; Task {feat['task_id']}</span> <span style="font-size:11px; color:#64748b; margin-left:8px;">{feat['language'].upper()}</span>{mismatch_tag}</div>
<div class="case-score" style="color:{oc}">{feat['overall']:.4f}</div>
</div>
<div class="case-question">{feat['question'][:200]}</div>
<div class="case-dims">'''

    for d_key, d_label in [('comp','Comp.'),('insight','Insight'),('instr','Instr.F.'),('read','Read.')]:
        v = feat[d_key]
        c = case_color(v)
        h += f'<div class="case-dim"><div class="dim-label">{d_label}</div><div class="dim-val" style="color:{c}">{v:.4f}</div></div>'

    h += f'''</div>
<div class="case-meta">
<div class="case-meta-item"><div class="meta-label">Report Length</div><div class="meta-val">{feat['report_len']:,}</div></div>
<div class="case-meta-item"><div class="meta-label">Reference Length</div><div class="meta-val">{feat['ref_len']:,}</div></div>
<div class="case-meta-item"><div class="meta-label">Length Ratio</div><div class="meta-val">{feat['len_ratio']:.2f}x</div></div>
<div class="case-meta-item"><div class="meta-label">URLs: {feat['urls']} | Tables: {feat['tables']} | CN Ratio: {feat['cn_ratio']:.0%} | Raw Target: {feat['raw_target']:.2f} / Ref: {feat['raw_ref']:.2f}</div></div>
</div>'''

    if feat['section_titles']:
        h += '<div class="case-sections"><div style="color:#64748b; margin-bottom:4px;">Section Outline:</div>'
        for s in feat['section_titles']:
            h += f'<div class="sec-title">{s[:70]}</div>'
        h += '</div>'

    h += '</div>'
    return h

# ===== TAB 1: Overview =====
tab1 = f"""
<div class="card">
<h2>Experiment Status</h2>
<div class="status-grid">
<div class="status-item"><div class="label">Step 1: Baseline</div><div class="value up">Done</div><div class="sub">50/50 items scored</div></div>
<div class="status-item"><div class="label">Step 2: V2 Inference</div><div class="value" style="color:#fbbf24;">Running</div><div class="sub">{n_v2}/50 completed</div></div>
<div class="status-item"><div class="label">Step 3: V2 RACE Eval</div><div class="value muted">Pending</div><div class="sub">After step 2</div></div>
<div class="status-item"><div class="label">Step 4: Compare + Viz</div><div class="value muted">Pending</div><div class="sub">After step 3</div></div>
</div>
<div class="progress-container">
<div style="margin-bottom:6px; font-size:12px; color:#94a3b8;">Step 2 Full Inference Progress (concurrency=2, ~50min/item)</div>
<div class="progress-bar"><div class="progress-fill" style="width:{n_v2/50*100:.1f}%"></div><div class="progress-text">{n_v2}/50 ({n_v2/50*100:.0f}%)</div></div>
</div>
</div>

<div class="card">
<h2>Official RACE Alignment Analysis</h2>
<div class="align-grid">
<div class="align-card">
<h3 style="color:#4ade80;">Fully Aligned (direct import from official code)</h3>
<div class="align-item"><span class="align-icon align-ok">&#10003;</span><span>Scoring Prompt (generate_merged_score_prompt zh/en)</span></div>
<div class="align-item"><span class="align-icon align-ok">&#10003;</span><span>Weighted Score Calculator (calculate_weighted_scores)</span></div>
<div class="align-item"><span class="align-icon align-ok">&#10003;</span><span>JSON Extraction (extract_json_from_markdown)</span></div>
<div class="align-item"><span class="align-icon align-ok">&#10003;</span><span>Normalization: target / (target + reference)</span></div>
<div class="align-item"><span class="align-icon align-ok">&#10003;</span><span>Article Assignment: article_1=target, article_2=reference</span></div>
<div class="align-item"><span class="align-icon align-ok">&#10003;</span><span>Criteria/Reference Matching (prompt field)</span></div>
<div class="align-item"><span class="align-icon align-ok">&#10003;</span><span>4-Dimension Validation</span></div>
</div>
<div class="align-card">
<h3 style="color:#fbbf24;">Differences</h3>
<table class="diff-table">
<tr><td class="diff-label">Judge Model</td><td>Official: <strong>Gemini 2.5 Pro</strong> + thinking<br/>Ours: <strong>Doubao Seed 1.6</strong>, temp=0.1</td><td><span class="diff-impact impact-high">HIGH</span></td></tr>
<tr><td class="diff-label">Article Cleaning</td><td>Official: ArticleCleaner<br/>Ours: None (raw report)</td><td><span class="diff-impact impact-mid">MID</span></td></tr>
<tr><td class="diff-label">Language Detection</td><td>Official: ground-truth label<br/>Ours: heuristic</td><td><span class="diff-impact impact-low">LOW</span></td></tr>
</table>
<p style="margin-top:10px; font-size:11px; color:#94a3b8;"><strong>Conclusion:</strong> Algorithm fully aligned. Relative comparison valid. Absolute scores not comparable to leaderboard.</p>
</div>
</div>
</div>

<div class="card">
<h2>Baseline RACE Scores (exp3, 50 items) <span class="badge badge-done">COMPLETE</span></h2>
<div class="score-grid">"""

for d in dims:
    val = baseline_avgs[d]
    c = "#4ade80" if val >= 0.5 else "#f87171"
    tab1 += f'<div class="score-card"><div class="dim">{dim_labels[d]}</div><div class="val" style="color:{c}">{val:.4f}</div></div>'

tab1 += """</div></div>"""

# V2 comparison bars
tab1 += """<div class="card"><h2>V2 Quick Validation: 2-Item RACE Test <span class="badge badge-done">COMPLETE</span></h2>
<div class="legend"><div class="legend-item"><div class="legend-dot" style="background:#64748b;"></div> Baseline (50-item avg)</div><div class="legend-item"><div class="legend-dot" style="background:#3b82f6;"></div> V2 (2-item avg)</div></div><div class="bar-section">"""
for d in dims:
    b, v = baseline_avgs[d], v2_test_avgs[d]
    delta = v - b
    dc = "up" if delta > 0 else "down"
    arrow = "+" if delta > 0 else ""
    tab1 += f'''<div class="bar-row"><div class="bar-label">{dim_labels[d]}</div><div style="flex:1;position:relative;"><div class="bar-track"><div class="bar-fill-top" style="width:{b*100:.1f}%;background:linear-gradient(90deg,#475569,#64748b);"></div><div class="bar-fill-bot" style="width:{v*100:.1f}%;background:linear-gradient(90deg,#2563eb,#3b82f6);"></div><div class="bar-mid"></div></div><span class="bar-val" style="top:25%;color:#94a3b8;">{b:.4f}</span><span class="bar-val" style="top:75%;color:#60a5fa;">{v:.4f}</span></div><span style="margin-left:80px;font-size:11px;font-weight:600;" class="{dc}">{arrow}{delta:.4f}</span></div>'''
tab1 += "</div></div>"

# Report quality
tab1 += f'''<div class="card"><h2>Report Quality: exp3 vs V2 ({n_v2} items)</h2><div class="two-col"><div><table>
<tr><th>Metric</th><th>exp3</th><th>V2</th><th>Ratio</th></tr>
<tr><td style="text-align:left;">Avg Report Length (chars)</td><td>{exp3_avg_len:,.0f}</td><td>{v2_avg_len:,.0f}</td><td class="up">{v2_avg_len/exp3_avg_len:.1f}x</td></tr>
<tr><td style="text-align:left;">Sections / Report</td><td>4-6</td><td>10</td><td class="up">~2x</td></tr>
<tr><td style="text-align:left;">Citations / Report</td><td>~10</td><td>60+</td><td class="up">~6x</td></tr>
<tr><td style="text-align:left;">Avg Time (s)</td><td>~300</td><td>~{v2_avg_time:,.0f}</td><td style="color:#fbbf24;">~{v2_avg_time/300:.0f}x</td></tr>
</table></div><div><table>
<tr><th colspan="2">V2 Architecture Changes</th></tr>
<tr><td style="text-align:left;color:#94a3b8;">max_section_steps</td><td>20 &rarr; 30</td></tr>
<tr><td style="text-align:left;color:#94a3b8;">summary_interval</td><td>6 &rarr; 8</td></tr>
<tr><td style="text-align:left;color:#94a3b8;">section_concurrency</td><td>5 &rarr; 4</td></tr>
<tr><td style="text-align:left;color:#94a3b8;">max_section_retries</td><td>2 &rarr; 3</td></tr>
<tr><td style="text-align:left;color:#94a3b8;">prompts_type</td><td>default &rarr; medical</td></tr>
</table></div></div></div>'''


# ===== TAB 2: Case Analysis =====
tab2 = ""

# Key Insights
tab2 += '''<div class="insight-box"><h3>Key Findings from Case Analysis</h3><ul>
<li><strong>Language Mismatch (Critical)</strong>: All 25 Chinese questions produced English-language reports (cn_ratio &lt; 15%). This is the most systemic issue.</li>
<li><strong>raw_target is the decisive factor</strong>: Correlation with overall score is <strong>+0.92</strong>. Higher absolute quality = higher score.</li>
<li><strong>Report length is NOT correlated</strong> with score (corr = -0.03). Content quality matters, not length.</li>
<li><strong>Insight is the universal weakness</strong>: 0/50 items scored above 0.5 on Insight. Mean = 0.3989. This is where the biggest gap exists.</li>
<li><strong>Instruction Following is the strongest dimension</strong>: 5/50 items above 0.5. Mean = 0.4681.</li>
<li><strong>URLs (citations) show negative correlation</strong> (corr = -0.23) -- having more URLs does not help; quality of analysis matters more.</li>
</ul></div>'''

# Correlation chart
tab2 += '<div class="card"><h2>Feature Correlation with Overall Score</h2>'
feat_labels = {
    'raw_target': 'Raw Target Score',
    'raw_ref': 'Raw Reference Score',
    'urls': 'URL Count',
    'ref_len': 'Reference Length',
    'report_len': 'Report Length',
    'len_ratio': 'Length Ratio (ours/ref)',
}
for feat_key in ['raw_target', 'len_ratio', 'report_len', 'ref_len', 'urls', 'raw_ref']:
    c = corr_data[feat_key]
    bar_color = "#4ade80" if c > 0.3 else ("#f87171" if c < -0.1 else "#94a3b8")
    # bar position: center at 50%, positive goes right, negative goes left
    if c >= 0:
        left_pct = 50
        width_pct = c * 50
    else:
        left_pct = 50 + c * 50
        width_pct = -c * 50
    tab2 += f'''<div class="corr-row">
<div class="corr-label">{feat_labels.get(feat_key, feat_key)}</div>
<div class="corr-bar-container"><div class="corr-bar-bg"></div><div class="corr-bar-center"></div><div class="corr-bar-fill" style="left:{left_pct}%;width:{width_pct}%;background:{bar_color};"></div></div>
<div class="corr-val" style="color:{bar_color};">{c:+.4f}</div>
</div>'''
tab2 += '</div>'

# Dimension Analysis
tab2 += '<div class="card"><h2>Dimension Analysis (all 50 items)</h2>'
tab2 += '<div style="margin-bottom:8px;font-size:11px;color:#64748b;">Yellow line = 0.5 (reference parity). Bar shows mean score. Green = above 0.5 exists.</div>'
for d in ['comprehensiveness', 'insight', 'instruction_following', 'readability']:
    da = dim_analysis[d]
    fill_color = "#f87171" if da['above_05'] == 0 else "#fbbf24" if da['above_05'] < 5 else "#4ade80"
    tab2 += f'''<div class="dim-bar-row">
<div class="dim-bar-label">{dim_labels[d]}</div>
<div class="dim-bar-track"><div class="dim-bar-fill" style="width:{da['mean']*100:.1f}%;background:{fill_color};border-radius:5px;"></div><div class="dim-bar-mid"></div></div>
<div class="dim-bar-stats">{da['mean']:.4f} ({da['above_05']}/{da['total']} &gt;0.5)</div>
</div>'''
tab2 += '</div>'

# Top 5 High Score
tab2 += '<div class="card"><h2 style="color:#4ade80;">Top 5 Highest Scoring Cases</h2>'
for i, feat in enumerate(top5_features):
    tab2 += render_case_card(feat, f"#{i+1}")
tab2 += '</div>'

# Bottom 5 Low Score
tab2 += '<div class="card"><h2 style="color:#f87171;">Bottom 5 Lowest Scoring Cases</h2>'
for i, feat in enumerate(bot5_features):
    tab2 += render_case_card(feat, f"#{50-len(bot5_features)+i+1}")
tab2 += '</div>'

# High vs Low comparison table
tab2 += '<div class="card"><h2>High vs Low Score Group Comparison</h2><table>'
tab2 += '<tr><th>Feature</th><th>Top 5 (High)</th><th>Bottom 5 (Low)</th><th>Interpretation</th></tr>'
# compute group stats
def group_stats(feats):
    return {
        'avg_overall': sum(f['overall'] for f in feats)/len(feats),
        'avg_report_len': sum(f['report_len'] for f in feats)/len(feats),
        'avg_ref_len': sum(f['ref_len'] for f in feats)/len(feats),
        'avg_len_ratio': sum(f['len_ratio'] for f in feats)/len(feats),
        'avg_urls': sum(f['urls'] for f in feats)/len(feats),
        'avg_raw_target': sum(f['raw_target'] for f in feats)/len(feats),
        'avg_raw_ref': sum(f['raw_ref'] for f in feats)/len(feats),
        'lang_mismatch': sum(1 for f in feats if f['lang_mismatch']),
    }
hi = group_stats(top5_features)
lo = group_stats(bot5_features)
rows = [
    ('Overall Score', f"{hi['avg_overall']:.4f}", f"{lo['avg_overall']:.4f}", 'Gap = {:.4f}'.format(hi['avg_overall']-lo['avg_overall'])),
    ('Raw Target Score', f"{hi['avg_raw_target']:.2f}", f"{lo['avg_raw_target']:.2f}", 'High group raw quality significantly better'),
    ('Raw Reference Score', f"{hi['avg_raw_ref']:.2f}", f"{lo['avg_raw_ref']:.2f}", 'Similar reference difficulty'),
    ('Avg Report Length', f"{hi['avg_report_len']:,.0f}", f"{lo['avg_report_len']:,.0f}", 'Almost same length -- length does NOT matter'),
    ('Avg Reference Length', f"{hi['avg_ref_len']:,.0f}", f"{lo['avg_ref_len']:,.0f}", 'Slightly shorter references in high group'),
    ('Length Ratio (ours/ref)', f"{hi['avg_len_ratio']:.2f}x", f"{lo['avg_len_ratio']:.2f}x", 'Both far below 1x'),
    ('Avg URLs', f"{hi['avg_urls']:.1f}", f"{lo['avg_urls']:.1f}", 'Low group has MORE urls -- urls dont help'),
    ('Lang Mismatch (zh)', f"{hi['lang_mismatch']}/5", f"{lo['lang_mismatch']}/5", 'Both groups have mismatch -- systemic issue'),
]
for label, h_val, l_val, interp in rows:
    tab2 += f'<tr><td style="text-align:left;font-weight:600;color:#94a3b8;">{label}</td><td style="color:#4ade80;">{h_val}</td><td style="color:#f87171;">{l_val}</td><td style="text-align:left;font-size:11px;color:#94a3b8;">{interp}</td></tr>'
tab2 += '</table></div>'


# ===== TAB 3: Detail =====
tab3 = ""

# V2 Completed Items
tab3 += f'''<div class="card"><h2>V2 Inference: Completed Items <span class="badge badge-running">{n_v2}/50</span></h2><div class="table-scroll"><table>
<tr><th>Task ID</th><th>Question</th><th>Report Length</th><th>Time (s)</th><th>Input Tokens</th><th>Output Tokens</th></tr>'''
for item in sorted(v2_details, key=lambda x: x["task_id"]):
    tab3 += f'''<tr><td>{item['task_id']}</td><td style="text-align:left;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{item['question']}">{item['question']}</td><td>{item['report_len']:,}</td><td>{item['total_time']:,.0f}</td><td>{item['input_tokens']:,}</td><td>{item['output_tokens']:,}</td></tr>'''
tab3 += '</table></div></div>'

# Baseline Per-Item Scores
tab3 += '''<div class="card"><h2>Baseline RACE: All 50 Items (sorted by Overall)</h2><div class="table-scroll"><table>
<tr><th>#</th><th>ID</th><th>Lang</th><th>Question</th><th>Comp.</th><th>Insight</th><th>Instr.F.</th><th>Read.</th><th>Overall</th></tr>'''
for i, item in enumerate(baseline_items):
    tab3 += f'''<tr><td>{i+1}</td><td>{item['task_id']}</td><td>{item['language']}</td><td style="text-align:left;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{item['question']}">{item['question']}</td><td>{color_val(item['comprehensiveness'])}</td><td>{color_val(item['insight'])}</td><td>{color_val(item['instruction_following'])}</td><td>{color_val(item['readability'])}</td><td>{color_val(item['overall_score'])}</td></tr>'''
tab3 += '''</table></div>
<p style="margin-top:8px;font-size:11px;color:#64748b;">Color: <span style="color:#4ade80;">green</span> >=0.50, <span style="color:#fbbf24;">yellow</span> 0.45-0.50, <span style="color:#f87171;">red</span> &lt;0.45</p></div>'''

# Next Steps
tab3 += f'''<div class="card"><h2>Next Steps</h2><ul class="step-list">
<li><strong>Monitor Step 2:</strong> <code>wc -l assets/output/report_v2_drb_med.jsonl</code> ({n_v2}/50, PID 36665)</li>
<li><strong>Step 3 RACE eval:</strong> <code>python3 step3_race_eval.py --input assets/output/report_v2_drb_med.jsonl --tag v2 2>&1 | tee assets/logs/step3_v2_full.log</code></li>
<li><strong>Step 4 compare:</strong> <code>python3 step4_compare.py</code></li>
<li><strong>Deploy:</strong> <code>show assets/output/comparison_report.html exp4_drb_compare "exp4 DRB RACE comparison"</code></li>
</ul></div>'''


# ===== Assemble HTML =====
html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>exp4_report_drb: Handoff Dashboard</title>
<style>{css}</style>
</head>
<body>
<div class="header">
<h1>exp4_report_drb: DRB RACE Evaluation & Report Optimization</h1>
<p class="subtitle">Handoff Dashboard &middot; 2025-02-25 &middot; Baseline (exp3) vs V2 (Optimized)</p>
</div>

<div class="tab-bar">
<button class="tab-btn active" onclick="switchTab('overview')">Overview</button>
<button class="tab-btn" onclick="switchTab('cases')">Case Analysis</button>
<button class="tab-btn" onclick="switchTab('detail')">Detail & Next Steps</button>
</div>

<div id="tab-overview" class="tab-content active">{tab1}</div>
<div id="tab-cases" class="tab-content">{tab2}</div>
<div id="tab-detail" class="tab-content">{tab3}</div>

<script>
function switchTab(name) {{
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    event.target.classList.add('active');
}}
</script>
</body>
</html>"""

output_path = os.path.join(BASE_DIR, 'assets/output/handoff_dashboard.html')
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"Generated: {output_path}")
print(f"HTML size: {len(html):,} bytes")
