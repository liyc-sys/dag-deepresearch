#!/usr/bin/env python3
# coding=utf-8
"""生成 liyc-sys 提交分析 HTML 报告"""

import json

commits = [
    {
        "hash": "ed9499c",
        "date": "2026-02-14 20:38",
        "title": "Add two-layer DAG deep research report generation",
        "theme": "Framework Foundation",
        "color": "#4f8ef7",
        "lines_added": 665,
        "lines_deleted": 1,
        "files_changed": 7,
        "summary": "建立两层DAG深度报告生成骨架，包含DAG数据结构、并发编排器、提示模板和CLI入口。",
        "files": [
            {"name": "FlashOAgents/report_dag.py", "type": "new", "lines": 122,
             "desc": "DAG数据结构：SectionStatus枚举、ReportSection、ReportOutline，含拓扑调度和环检测"},
            {"name": "FlashOAgents/report_orchestrator.py", "type": "new", "lines": 326,
             "desc": "Layer1编排器：plan_report / execute_report / synthesize_report，ThreadPoolExecutor并发"},
            {"name": "FlashOAgents/prompts/report/report_prompts.yaml", "type": "new", "lines": 124,
             "desc": "三类Jinja2提示模板：报告规划、章节研究（带依赖上下文）、报告合成"},
            {"name": "run_deep_report.py", "type": "new", "lines": 82,
             "desc": "CLI入口：argparse参数解析，串联plan→execute→synthesize三阶段"},
            {"name": "run_deep_report.sh", "type": "new", "lines": 7,
             "desc": "Shell运行脚本"},
            {"name": "FlashOAgents/__init__.py", "type": "modified", "lines": 4,
             "desc": "新增report_dag和report_orchestrator的模块导入"},
            {"name": ".gitignore", "type": "modified", "lines": 1,
             "desc": "排除__pycache__目录"},
        ],
        "highlights": [
            "ReportOutline.get_ready_sections()：依赖满足则立即标记READY",
            "validate_dag()：DFS白灰黑三色法检测环路",
            "execute_report()：FIRST_COMPLETED即时调度，完成即提交新任务",
            "plan_report()：最多3次重试 + json_repair兼容LLM非标准JSON",
            "get_completed_context()：截断至2000字符作为下游依赖上下文",
        ]
    },
    {
        "hash": "03e1efb",
        "date": "2026-02-15 15:01",
        "title": "feat: add token tracking, timing instrumentation and Gantt visualization",
        "theme": "Observability",
        "color": "#f7904f",
        "lines_added": 1990,
        "lines_deleted": 117,
        "files_changed": 10,
        "summary": "全链路埋点：LLM调用时间、Token消耗从step级到章节级全面记录，并新增甘特图可视化工具。",
        "files": [
            {"name": "visualize_dag.py", "type": "new", "lines": 1132,
             "desc": "静态HTML生成器：DAG节点图、甘特时间线、详情面板（含token/时间统计）"},
            {"name": "test_token_timing.py", "type": "new", "lines": 687,
             "desc": "33个单元测试：覆盖ToolCall/ActionStep/PlanningStep时间token字段及HTML生成"},
            {"name": "FlashOAgents/memory.py", "type": "modified", "lines": 28,
             "desc": "ToolCall+start/end/duration; ActionStep+input/output_tokens+llm时间; PlanningStep/SummaryStep同步"},
            {"name": "FlashOAgents/agents.py", "type": "modified", "lines": 196,
             "desc": "LLM调用前后time.time()打点，usage.prompt_tokens/completion_tokens存入step"},
            {"name": "FlashOAgents/models.py", "type": "modified", "lines": 4,
             "desc": "ChatMessage新增input_token_count/output_token_count（线程安全）"},
            {"name": "FlashOAgents/report_dag.py", "type": "modified", "lines": 10,
             "desc": "ReportSection新增wall_clock_time、total_input/output_tokens"},
            {"name": "FlashOAgents/report_orchestrator.py", "type": "modified", "lines": 29,
             "desc": "记录章节挂钟时间，聚合各步骤token到ReportSection"},
            {"name": "base_agent.py", "type": "modified", "lines": 14,
             "desc": "capture_trajectory()序列化新增的时间/token字段"},
            {"name": "run_deep_report.py", "type": "modified", "lines": 6,
             "desc": "报告生成后自动调用visualize_dag.py生成HTML"},
            {"name": ".gitignore", "type": "modified", "lines": 1,
             "desc": "补充忽略规则"},
        ],
        "highlights": [
            "三层埋点：ToolCall粒度→ActionStep/PlanningStep粒度→ReportSection粒度",
            "线程安全：ChatMessage的token累加使用threading.Lock",
            "甘特图：章节级并行执行时间轴，直观展示并发效率",
            "33个单测覆盖全部新功能，包括HTML生成的正确性验证",
            "run_deep_report.py报告完成后自动生成可视化",
        ]
    },
    {
        "hash": "0f286a2",
        "date": "2026-02-17 12:47",
        "title": "feat: add goal/path tracking, topic_file support, and tuning updates",
        "theme": "Traceability & Tuning",
        "color": "#4fc97f",
        "lines_added": 73,
        "lines_deleted": 11,
        "files_changed": 9,
        "summary": "为工具调用打上Goal/Path标签实现计划-行动端到端追踪；支持长主题从文件读入；并行度和上下文长度参数大幅调优。",
        "files": [
            {"name": "FlashOAgents/memory.py", "type": "modified", "lines": 18,
             "desc": "ToolCall新增goal/path字段；ActionStep的assistant消息前置推理文本Reasoning"},
            {"name": "FlashOAgents/agents.py", "type": "modified", "lines": 9,
             "desc": "从LLM输出tool_call中解析goal/path，写入ToolCall对象；日志行附加[Goal/Path]标签"},
            {"name": "FlashOAgents/prompts/default/toolcalling_agent.yaml", "type": "modified", "lines": 7,
             "desc": "提示模板要求LLM在每个tool_call中输出goal和path字段，含3个示例"},
            {"name": "run_deep_report.py", "type": "modified", "lines": 22,
             "desc": "--topic_file参数：从文件读取长主题；topic_file优先级高于--topic"},
            {"name": "visualize_dag.py", "type": "modified", "lines": 5,
             "desc": "详情面板中展示tool_call的goal/path标签"},
            {"name": "run_deep_report.sh", "type": "modified", "lines": 7,
             "desc": "更新运行示例脚本"},
            {"name": "topic/1.txt", "type": "new", "lines": 13,
             "desc": "示例长主题文本文件"},
            {"name": "开发记录.txt", "type": "new", "lines": 16,
             "desc": "中文开发笔记"},
            {"name": "FlashOAgents/report_dag.py", "type": "modified", "lines": 2,
             "desc": "max_chars_per_section默认值2000→8000"},
        ],
        "highlights": [
            "Goal/Path数据流：yaml提示→LLM输出→agents.py解析→ToolCall.goal/path→日志/可视化",
            "assistant消息增强：先输出Reasoning推理文本再输出工具调用，提升上下文语义",
            "topic_file：支持从文件读入长主题，topic_file优先级高于--topic参数",
            "summary_interval: 6→8（减少中间摘要频率）",
            "section_concurrency: 5→10（并发章节数翻倍）",
            "max_chars_per_section: 2000→8000（依赖上下文长度扩大4倍）",
        ]
    }
]

params_comparison = [
    {"param": "summary_interval", "before": 6, "after": 8, "unit": "", "change": "+33%", "commit": "0f286a2"},
    {"param": "section_concurrency", "before": 5, "after": 10, "unit": "", "change": "+100%", "commit": "0f286a2"},
    {"param": "max_chars_per_section", "before": 2000, "after": 8000, "unit": "chars", "change": "+300%", "commit": "0f286a2"},
]

html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>liyc-sys Commit Analysis — dag-deepresearch</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f1117; color: #e0e0e0; line-height: 1.6; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px; }}

  /* Header */
  .header {{ text-align: center; margin-bottom: 48px; }}
  .header h1 {{ font-size: 2.2rem; font-weight: 700; color: #fff; margin-bottom: 8px; }}
  .header .subtitle {{ color: #888; font-size: 1rem; }}
  .header .meta {{ display: inline-flex; gap: 24px; margin-top: 16px; background: #1a1d27; border-radius: 8px; padding: 12px 24px; }}
  .header .meta-item {{ text-align: center; }}
  .header .meta-item .val {{ font-size: 1.8rem; font-weight: 700; color: #4f8ef7; }}
  .header .meta-item .lbl {{ font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 0.05em; }}

  /* Timeline */
  .timeline {{ position: relative; margin-bottom: 56px; }}
  .timeline-line {{ position: absolute; left: 28px; top: 0; bottom: 0; width: 2px; background: linear-gradient(to bottom, #4f8ef7, #f7904f, #4fc97f); opacity: 0.4; }}
  .commit-card {{ position: relative; padding-left: 68px; margin-bottom: 40px; }}
  .commit-dot {{ position: absolute; left: 18px; top: 20px; width: 22px; height: 22px; border-radius: 50%; border: 3px solid #1a1d27; z-index: 1; }}
  .commit-header {{ background: #1a1d27; border-radius: 12px 12px 0 0; padding: 20px 24px; border-left: 4px solid var(--accent); display: flex; align-items: flex-start; gap: 16px; flex-wrap: wrap; }}
  .commit-hash {{ font-family: monospace; font-size: 0.8rem; background: #252836; padding: 4px 10px; border-radius: 6px; color: #aaa; white-space: nowrap; }}
  .commit-date {{ font-size: 0.85rem; color: #888; white-space: nowrap; }}
  .commit-title {{ font-size: 1.05rem; font-weight: 600; color: #fff; flex: 1; min-width: 200px; }}
  .commit-theme {{ font-size: 0.8rem; padding: 3px 10px; border-radius: 12px; font-weight: 600; white-space: nowrap; }}
  .commit-body {{ background: #141720; border-radius: 0 0 12px 12px; padding: 20px 24px; }}
  .commit-summary {{ color: #b0b0c0; margin-bottom: 16px; font-size: 0.95rem; }}
  .stats-row {{ display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }}
  .stat-badge {{ background: #252836; border-radius: 6px; padding: 6px 12px; font-size: 0.82rem; }}
  .stat-badge .num {{ font-weight: 700; margin-right: 4px; }}
  .stat-plus {{ color: #4fc97f; }}
  .stat-minus {{ color: #f76060; }}
  .stat-files {{ color: #f7904f; }}

  /* Files table */
  .files-toggle {{ cursor: pointer; color: #4f8ef7; font-size: 0.88rem; margin-bottom: 10px; user-select: none; }}
  .files-toggle:hover {{ text-decoration: underline; }}
  .files-table {{ width: 100%; border-collapse: collapse; font-size: 0.84rem; display: none; }}
  .files-table.open {{ display: table; }}
  .files-table th {{ background: #252836; color: #888; font-weight: 600; text-align: left; padding: 8px 12px; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; }}
  .files-table td {{ padding: 8px 12px; border-bottom: 1px solid #1e2132; color: #c0c0d0; }}
  .files-table tr:last-child td {{ border-bottom: none; }}
  .badge-new {{ background: #1a3a20; color: #4fc97f; padding: 2px 7px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }}
  .badge-mod {{ background: #2a2a12; color: #f7c94f; padding: 2px 7px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }}
  .fname {{ font-family: monospace; color: #9ab4f7; }}

  /* Highlights */
  .highlights {{ margin-top: 16px; }}
  .highlights h4 {{ font-size: 0.82rem; color: #888; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }}
  .highlight-list {{ list-style: none; }}
  .highlight-list li {{ padding: 5px 0 5px 18px; position: relative; color: #c0c0d0; font-size: 0.88rem; border-bottom: 1px solid #1e2132; }}
  .highlight-list li:last-child {{ border-bottom: none; }}
  .highlight-list li::before {{ content: "▸"; position: absolute; left: 0; color: var(--accent); }}

  /* Params section */
  .section-title {{ font-size: 1.3rem; font-weight: 700; color: #fff; margin-bottom: 20px; padding-bottom: 8px; border-bottom: 2px solid #252836; }}
  .params-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 48px; }}
  .param-card {{ background: #1a1d27; border-radius: 12px; padding: 20px; border: 1px solid #252836; }}
  .param-name {{ font-family: monospace; font-size: 0.95rem; color: #9ab4f7; margin-bottom: 12px; font-weight: 600; }}
  .param-arrow {{ display: flex; align-items: center; gap: 12px; }}
  .param-before {{ font-size: 1.3rem; color: #888; font-weight: 700; }}
  .param-after {{ font-size: 1.6rem; color: #4fc97f; font-weight: 700; }}
  .arrow-icon {{ color: #f7904f; font-size: 1.2rem; }}
  .param-change {{ margin-top: 8px; font-size: 0.82rem; }}
  .change-positive {{ color: #4fc97f; }}

  /* Architecture diagram */
  .arch-diagram {{ background: #1a1d27; border-radius: 12px; padding: 24px; margin-bottom: 48px; font-family: monospace; font-size: 0.88rem; color: #c0c0d0; line-height: 1.8; white-space: pre-wrap; border: 1px solid #252836; overflow-x: auto; }}

  /* Evolution timeline */
  .evolution {{ display: flex; gap: 0; margin-bottom: 48px; }}
  .evo-item {{ flex: 1; background: #1a1d27; padding: 20px; text-align: center; position: relative; border: 1px solid #252836; }}
  .evo-item:first-child {{ border-radius: 12px 0 0 12px; }}
  .evo-item:last-child {{ border-radius: 0 12px 12px 0; }}
  .evo-arrow {{ position: absolute; right: -16px; top: 50%; transform: translateY(-50%); color: #f7904f; font-size: 1.4rem; z-index: 1; }}
  .evo-phase {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #888; margin-bottom: 8px; }}
  .evo-label {{ font-size: 1rem; font-weight: 700; color: #fff; margin-bottom: 4px; }}
  .evo-desc {{ font-size: 0.8rem; color: #888; }}

  /* Responsive */
  @media (max-width: 700px) {{
    .header .meta {{ flex-wrap: wrap; }}
    .evolution {{ flex-direction: column; }}
    .evo-item:first-child {{ border-radius: 12px 12px 0 0; }}
    .evo-item:last-child {{ border-radius: 0 0 12px 12px; }}
    .evo-arrow {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>liyc-sys Commit Analysis</h1>
    <div class="subtitle">Repository: dag-deepresearch &nbsp;·&nbsp; 2026-02-14 to 2026-02-17</div>
    <div class="meta">
      <div class="meta-item"><div class="val">3</div><div class="lbl">Commits</div></div>
      <div class="meta-item"><div class="val" style="color:#4fc97f">+2728</div><div class="lbl">Lines Added</div></div>
      <div class="meta-item"><div class="val" style="color:#f76060">−129</div><div class="lbl">Lines Deleted</div></div>
      <div class="meta-item"><div class="val" style="color:#f7904f">18</div><div class="lbl">Files Changed</div></div>
      <div class="meta-item"><div class="val" style="color:#c97ff7">33</div><div class="lbl">Test Cases</div></div>
    </div>
  </div>

  <div class="section-title">Evolution Path</div>
  <div class="evolution">
    <div class="evo-item">
      <div class="evo-phase">Feb 14 · ed9499c</div>
      <div class="evo-label" style="color:#4f8ef7">Foundation</div>
      <div class="evo-desc">Two-layer DAG<br>framework skeleton</div>
      <div class="evo-arrow">→</div>
    </div>
    <div class="evo-item">
      <div class="evo-phase">Feb 15 · 03e1efb</div>
      <div class="evo-label" style="color:#f7904f">Observability</div>
      <div class="evo-desc">Token tracking<br>+ Gantt visualization</div>
      <div class="evo-arrow">→</div>
    </div>
    <div class="evo-item">
      <div class="evo-phase">Feb 17 · 0f286a2</div>
      <div class="evo-label" style="color:#4fc97f">Traceability</div>
      <div class="evo-desc">Goal/Path tags<br>+ param tuning</div>
    </div>
  </div>

  <div class="section-title">Commit Details</div>
  <div class="timeline" id="timeline">
    <div class="timeline-line"></div>
  </div>

  <div class="section-title">Parameter Changes (0f286a2)</div>
  <div class="params-grid" id="params-grid"></div>

  <div class="section-title">Architecture Overview</div>
  <div class="arch-diagram">CLI: run_deep_report.py  [--topic / --topic_file]
  │
  └── Layer 1: ReportOrchestrator
        │
        ├── plan_report(topic)
        │     └── LLM → JSON outline → ReportOutline (DAG)
        │           validate_dag(): DFS cycle detection
        │
        ├── execute_report(outline)
        │     └── ThreadPoolExecutor (concurrency=10)
        │           FIRST_COMPLETED scheduling
        │           │
        │           └── Layer 2: SearchAgent (one per section)
        │                 ├── ToolCallingAgent.run()
        │                 │     ├── PlanningStep  [tokens + timing]
        │                 │     ├── ActionStep    [tokens + timing]
        │                 │     │     └── ToolCall [goal + path + timing]
        │                 │     └── SummaryStep   [tokens + timing]
        │                 └── returns research_result + trajectory
        │
        └── synthesize_report(outline)
              └── LLM → final Markdown report

Post-run: visualize_dag.py → static HTML
  ├── DAG node graph (status + tokens per node)
  ├── Gantt timeline (section-level wall-clock time)
  └── Detail panel (per-step LLM time + tokens + goal/path tags)</div>

</div>

<script>
const DATA = {json.dumps({"commits": commits, "params": params_comparison}, ensure_ascii=False)};

// Render timeline
const timeline = document.getElementById('timeline');
DATA.commits.forEach(c => {{
  const card = document.createElement('div');
  card.className = 'commit-card';
  card.style.setProperty('--accent', c.color);

  const dot = document.createElement('div');
  dot.className = 'commit-dot';
  dot.style.background = c.color;
  card.appendChild(dot);

  const filesHtml = c.files.map(f => `
    <tr>
      <td class="fname">${{f.name}}</td>
      <td><span class="${{f.type === 'new' ? 'badge-new' : 'badge-mod'}}">${{f.type === 'new' ? 'NEW' : 'MOD'}}</span></td>
      <td>${{f.lines}}</td>
      <td>${{f.desc}}</td>
    </tr>
  `).join('');

  const highlightsHtml = c.highlights.map(h => `<li>${{h}}</li>`).join('');

  card.innerHTML += `
    <div class="commit-header">
      <div>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:6px">
          <span class="commit-hash">${{c.hash}}</span>
          <span class="commit-date">${{c.date}}</span>
          <span class="commit-theme" style="background:${{c.color}}22;color:${{c.color}}">${{c.theme}}</span>
        </div>
        <div class="commit-title">${{c.title}}</div>
      </div>
    </div>
    <div class="commit-body">
      <div class="commit-summary">${{c.summary}}</div>
      <div class="stats-row">
        <div class="stat-badge"><span class="num stat-plus">+${{c.lines_added}}</span> lines added</div>
        <div class="stat-badge"><span class="num stat-minus">-${{c.lines_deleted}}</span> lines deleted</div>
        <div class="stat-badge"><span class="num stat-files">${{c.files_changed}}</span> files</div>
      </div>
      <div class="files-toggle" onclick="this.nextElementSibling.classList.toggle('open'); this.textContent = this.nextElementSibling.classList.contains('open') ? '▾ Hide file list' : '▸ Show file list (${{c.files.length}} files)'">▸ Show file list (${{c.files.length}} files)</div>
      <table class="files-table">
        <thead><tr><th>File</th><th>Type</th><th>Lines</th><th>Description</th></tr></thead>
        <tbody>${{filesHtml}}</tbody>
      </table>
      <div class="highlights">
        <h4>Key Highlights</h4>
        <ul class="highlight-list" style="--accent: ${{c.color}}">${{highlightsHtml}}</ul>
      </div>
    </div>
  `;
  timeline.appendChild(card);
}});

// Render params
const paramsGrid = document.getElementById('params-grid');
DATA.params.forEach(p => {{
  const card = document.createElement('div');
  card.className = 'param-card';
  card.innerHTML = `
    <div class="param-name">${{p.param}}</div>
    <div class="param-arrow">
      <div class="param-before">${{p.before}}${{p.unit}}</div>
      <div class="arrow-icon">→</div>
      <div class="param-after">${{p.after}}${{p.unit}}</div>
    </div>
    <div class="param-change"><span class="change-positive">${{p.change}}</span> &nbsp;·&nbsp; commit ${{p.commit}}</div>
  `;
  paramsGrid.appendChild(card);
}});
</script>
</body>
</html>
"""

out_path = "/mnt/bn/med-mllm-lfv2/linjh/project/learn/2026_q1/eval/dag-deepresearch/work/exp1_hello/docs/task1/commit_analysis.html"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Generated: {out_path}")
