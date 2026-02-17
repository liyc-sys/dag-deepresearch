#!/usr/bin/env python
# coding=utf-8

import json
import argparse
import html
import os
import re


def _parse_goal_path_structure(plan_text):
    """Parse Goal/Path structure from plan or summary text.

    Returns list of dicts:
    [
        {
            "goal_id": "1",
            "goal_title": "...",
            "paths": [
                {"path_id": "1.1", "path_title": "...", "success": "..."},
                ...
            ]
        },
        ...
    ]
    """
    if not plan_text:
        return []

    # Strip surrounding quotes and unescape if the value is a JSON-escaped string
    text = plan_text.strip()
    if text.startswith('"'):
        try:
            text = json.loads(text)
        except Exception:
            # Just strip the leading quote
            text = text.lstrip('"').rstrip('"')
    # Also handle literal \n sequences that weren't unescaped
    if "\\n" in text and "\n" not in text:
        text = text.replace("\\n", "\n")

    goals = []
    current_goal = None

    for line in text.split("\n"):
        line = line.strip()

        # Match "## Goal N: ..." or "### Goal N: ..."
        m = re.match(r'#{2,3}\s*Goal\s+(\d+):\s*(.*)', line)
        if m:
            current_goal = {
                "goal_id": m.group(1),
                "goal_title": m.group(2).strip(),
                "paths": [],
            }
            goals.append(current_goal)
            continue

        # Match numbered list form: "1. Goal 1: ..." or "1. Goal 1 (title): ..."
        num_match = re.match(r'(\d+)\.\s*Goal\s+\d+\s*[\(:](.*)$', line)
        if num_match and not line.startswith("#"):
            title = num_match.group(2).strip()
            # Remove trailing ")" if title was in parens format "1. Goal 1 (title): Path..."
            title = re.sub(r'\):\s*Path.*$', '', title).strip('() ')
            if not title:
                title = line
            current_goal = {
                "goal_id": num_match.group(1),
                "goal_title": title,
                "paths": [],
            }
            goals.append(current_goal)
            # Also extract inline paths like "Path 1.1 (...) and Path 1.2 (...)"
            inline_paths = re.findall(r'Path\s+(\d+\.\d+)\s*\(([^)]*)\)', line)
            for pid, ptitle in inline_paths:
                current_goal["paths"].append({
                    "path_id": pid,
                    "path_title": ptitle.strip(),
                    "success": "",
                })
            continue

        # Match "- Path N.M: ..." or "  - Path N.M (...)"
        path_match = re.match(r'-\s*Path\s+(\d+\.\d+)[\s:]+(.*)$', line)
        if path_match and current_goal is not None:
            current_goal["paths"].append({
                "path_id": path_match.group(1),
                "path_title": path_match.group(2).strip(),
                "success": "",
            })
            continue

        # Match "  - Success: ..."
        success_match = re.match(r'-\s*Success:\s*(.*)', line)
        if success_match and current_goal is not None and current_goal["paths"]:
            current_goal["paths"][-1]["success"] = success_match.group(1).strip()

    # Deduplicate by goal_id, keeping the last (usually more detailed) occurrence
    seen = {}
    for g in goals:
        seen[g["goal_id"]] = g
    return list(seen.values())


def _parse_summary_status(summary_text):
    """Parse execution status from summary text.

    Returns dict: { goal_id: { "status": "...", "paths": { path_id: "status_text" } } }
    """
    if not summary_text:
        return {}

    # Strip surrounding quotes and unescape if JSON-escaped
    text = summary_text.strip()
    if text.startswith('"'):
        try:
            text = json.loads(text)
        except Exception:
            text = text.lstrip('"').rstrip('"')
    if "\\n" in text and "\n" not in text:
        text = text.replace("\\n", "\n")

    result = {}
    current_goal_id = None

    for line in text.split("\n"):
        line = line.strip()

        # Match "### Goal N: ..." or "## Goal N: ..."
        goal_match = re.match(r'#{2,3}\s*Goal\s+(\d+):', line)
        if goal_match:
            current_goal_id = goal_match.group(1)
            if current_goal_id not in result:
                result[current_goal_id] = {"status": "", "paths": {}}
            continue

        # Match "- Status: ..."
        if line.startswith("- Status:") and current_goal_id:
            result[current_goal_id]["status"] = line.replace("- Status:", "").strip()
            continue

        # Match "- Path N.M (...): rest..." - determine status from full line context
        path_match = re.match(r'-\s*Path\s+(\d+\.\d+)\s*\(([^)]*)\)', line)
        if path_match and current_goal_id:
            pid = path_match.group(1)
            # Determine status from the text that follows
            rest = line[path_match.end():].lower()
            full_lower = line.lower()
            status = "pending"
            if "failed" in rest or "blocked" in full_lower or "uninitiated" in full_lower:
                status = "blocked"
            elif "success" in rest or "completed" in full_lower or "yielded" in rest:
                status = "completed"
            elif "partial" in full_lower:
                status = "partial"
            elif any(kw in rest for kw in ["search", "crawl", "multiple", "retrieved", "extracted"]):
                status = "in_progress"
            else:
                status = "in_progress"
            result[current_goal_id]["paths"][pid] = status
            continue

        # Also match path status in "Path Analysis:" sections
        # "- Path N.M (description): detailed analysis..."
        path_analysis = re.match(r'-\s*Path\s+(\d+\.\d+)\s+\(', line)
        if path_analysis and current_goal_id:
            pid = path_analysis.group(1)
            if pid not in result[current_goal_id].get("paths", {}):
                full_lower = line.lower()
                status = "pending"
                if "failed" in full_lower or "uninitiated" in full_lower or "no attempt" in full_lower:
                    status = "blocked"
                elif "inefficient" in full_lower or "blocked" in full_lower:
                    status = "blocked"
                elif "success" in full_lower or "completed" in full_lower:
                    status = "completed"
                elif "yielded" in full_lower or "retrieved" in full_lower or "extracted" in full_lower:
                    status = "partial"
                else:
                    status = "in_progress"
                result[current_goal_id]["paths"][pid] = status

    return result


def _compute_layout(sections):
    """Compute layered layout via topological sorting. Returns {section_id: (x, y)}."""
    # Build dependency info
    dep_map = {s["section_id"]: set(s.get("depends_on", [])) for s in sections}
    all_ids = [s["section_id"] for s in sections]

    # Assign layers: layer 0 = no dependencies, layer N = max(dep layers) + 1
    layers = {}
    def get_layer(sid):
        if sid in layers:
            return layers[sid]
        deps = dep_map.get(sid, set())
        if not deps:
            layers[sid] = 0
            return 0
        layer = max(get_layer(d) for d in deps) + 1
        layers[sid] = layer
        return layer

    for sid in all_ids:
        get_layer(sid)

    # Group by layer
    layer_groups = {}
    for sid, layer in layers.items():
        layer_groups.setdefault(layer, []).append(sid)

    # Sort within each layer by section_id for determinism
    for layer in layer_groups:
        layer_groups[layer].sort()

    max_layer = max(layer_groups.keys()) if layer_groups else 0
    node_w, node_h = 220, 60
    h_gap, v_gap = 280, 100

    layout = {}
    for layer, sids in layer_groups.items():
        x = 80 + layer * h_gap
        total_height = len(sids) * node_h + (len(sids) - 1) * (v_gap - node_h)
        start_y = 80 + (500 - total_height) / 2  # center vertically in ~500px
        for i, sid in enumerate(sids):
            y = start_y + i * v_gap
            layout[sid] = (x, y)

    return layout, node_w, node_h


def _escape(text):
    return html.escape(str(text)) if text else ""


def visualize_report_dag(meta_path, output_path=None):
    """Generate an interactive HTML visualization from a report meta JSON file."""
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    outline = meta["outline"]
    metadata = meta.get("metadata", {})
    sections = outline["sections"]

    if output_path is None:
        output_path = os.path.splitext(meta_path)[0].replace("_meta", "_dag") + ".html"

    layout, node_w, node_h = _compute_layout(sections)

    # Compute SVG dimensions
    if layout:
        max_x = max(x for x, y in layout.values()) + node_w + 80
        max_y = max(y for x, y in layout.values()) + node_h + 80
    else:
        max_x, max_y = 600, 400

    svg_width = max(max_x, 600)
    svg_height = max(max_y, 300)

    # Status colors
    status_colors = {
        "completed": "#4CAF50",
        "failed": "#F44336",
        "pending": "#9E9E9E",
        "ready": "#2196F3",
        "in_progress": "#FF9800",
    }
    status_border = {
        "completed": "#388E3C",
        "failed": "#C62828",
        "pending": "#616161",
        "ready": "#1565C0",
        "in_progress": "#E65100",
    }

    # Build SVG edges
    edges_svg = []
    for s in sections:
        sid = s["section_id"]
        sx, sy = layout[sid]
        for dep_id in s.get("depends_on", []):
            if dep_id in layout:
                dx, dy = layout[dep_id]
                # Arrow from dep (right side) to this node (left side)
                x1 = dx + node_w
                y1 = dy + node_h / 2
                x2 = sx
                y2 = sy + node_h / 2
                # Curve control points
                cx1 = x1 + 40
                cx2 = x2 - 40
                edges_svg.append(
                    f'<path d="M{x1},{y1} C{cx1},{y1} {cx2},{y2} {x2},{y2}" '
                    f'fill="none" stroke="#666" stroke-width="2" marker-end="url(#arrow)"/>'
                )

    # Build SVG nodes
    nodes_svg = []
    for s in sections:
        sid = s["section_id"]
        x, y = layout[sid]
        status = s.get("status", "pending")
        fill = status_colors.get(status, "#9E9E9E")
        border = status_border.get(status, "#616161")
        title = s["title"]
        # Truncate title
        display_title = title if len(title) <= 28 else title[:26] + "..."
        traj_len = len(s.get("trajectory") or [])
        section_total_tokens = (s.get("total_input_tokens") or 0) + (s.get("total_output_tokens") or 0)
        section_duration = s.get("section_duration")
        duration_str = f"{section_duration:.0f}s" if section_duration else ""
        bottom_text = f"{traj_len} steps"
        if section_total_tokens:
            bottom_text += f" | {section_total_tokens:,} tok"
        if duration_str:
            bottom_text += f" | {duration_str}"

        nodes_svg.append(f'''
        <g class="node" data-sid="{_escape(sid)}" style="cursor:pointer">
          <rect x="{x}" y="{y}" width="{node_w}" height="{node_h}" rx="8" ry="8"
                fill="{fill}" stroke="{border}" stroke-width="2" opacity="0.9"/>
          <text x="{x + node_w/2}" y="{y + 22}" text-anchor="middle"
                fill="white" font-size="13" font-weight="bold" pointer-events="none">{_escape(sid)}</text>
          <text x="{x + node_w/2}" y="{y + 40}" text-anchor="middle"
                fill="white" font-size="11" pointer-events="none">{_escape(display_title)}</text>
          <text x="{x + node_w/2}" y="{y + 54}" text-anchor="middle"
                fill="rgba(255,255,255,0.7)" font-size="9" pointer-events="none">{_escape(bottom_text)}</text>
        </g>''')

    # Prepare section data for JS with rich step details
    section_data_js = {}
    for s in sections:
        sid = s["section_id"]
        traj = s.get("trajectory") or []
        steps_summary = []
        for i, step in enumerate(traj):
            name = step.get("name", "unknown")
            think = (step.get("think") or "")[:1000]
            step_timing = {
                "start_time": step.get("start_time"),
                "end_time": step.get("end_time"),
                "duration": step.get("duration"),
                "input_tokens": step.get("input_tokens"),
                "output_tokens": step.get("output_tokens"),
            }
            if name == "plan":
                plan_text = step.get("value") or ""
                goals = _parse_goal_path_structure(plan_text)
                steps_summary.append({"idx": i, "type": "plan", "detail": plan_text, "think": think, "goals": goals, **step_timing})
            elif name == "summary":
                summary_text = step.get("value") or ""
                goals = _parse_goal_path_structure(summary_text)
                status_map = _parse_summary_status(summary_text)
                steps_summary.append({"idx": i, "type": "summary", "detail": summary_text, "think": think, "goals": goals, "status_map": status_map, **step_timing})
            elif name == "action":
                tool_calls = step.get("tool_calls") or []
                calls_detail = []
                for tc in tool_calls:
                    tn = tc.get("name", "?")
                    args = tc.get("arguments", {})
                    call_info = {"tool": tn, "duration": tc.get("duration"), "goal": tc.get("goal"), "path": tc.get("path")}
                    if tn == "web_search":
                        call_info["query"] = args.get("query", "")
                    elif tn == "crawl_page":
                        call_info["url"] = args.get("url", "")
                        call_info["query"] = args.get("query", "")[:200]
                    elif tn == "final_answer":
                        call_info["answer"] = (args.get("answer") or "")[:500]
                    else:
                        call_info["args"] = {k: str(v)[:200] for k, v in args.items()}
                    calls_detail.append(call_info)
                obs = (step.get("obs") or "")[:2000]
                steps_summary.append({
                    "idx": i, "type": "action",
                    "num_calls": len(tool_calls),
                    "calls": calls_detail,
                    "obs": obs,
                    "think": think,
                    "llm_duration": step.get("llm_duration"),
                    **step_timing,
                })

        section_data_js[sid] = {
            "section_id": sid,
            "title": s["title"],
            "description": s.get("description", ""),
            "research_query": s.get("research_query", ""),
            "depends_on": s.get("depends_on", []),
            "status": s.get("status", "pending"),
            "result_len": len(s.get("research_result") or ""),
            "research_result": s.get("research_result") or "",
            "error_message": s.get("error_message"),
            "retry_count": s.get("retry_count", 0),
            "steps": steps_summary,
            "section_start_time": s.get("section_start_time"),
            "section_end_time": s.get("section_end_time"),
            "section_duration": s.get("section_duration"),
            "total_input_tokens": s.get("total_input_tokens"),
            "total_output_tokens": s.get("total_output_tokens"),
        }

    # Build HTML
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DAG Visualization - {_escape(outline.get("title", "Report"))}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #1a1a2e; color: #e0e0e0; }}
#header {{ background: #16213e; padding: 20px 30px; border-bottom: 1px solid #333; }}
#header h1 {{ font-size: 18px; color: #fff; margin-bottom: 6px; }}
#header .meta {{ font-size: 13px; color: #999; }}
#header .meta span {{ margin-right: 20px; }}
#legend {{ padding: 10px 30px; display: flex; gap: 16px; font-size: 12px; background: #16213e; border-bottom: 1px solid #222; }}
.legend-item {{ display: flex; align-items: center; gap: 5px; }}
.legend-dot {{ width: 12px; height: 12px; border-radius: 3px; }}
#dag-container {{ padding: 20px; overflow-x: auto; background: #0f0f23; }}
#detail-panel {{ display: none; margin: 20px; background: #16213e; border-radius: 10px; border: 1px solid #333; overflow: hidden; }}
#detail-header {{ padding: 16px 20px; background: #1a1a3e; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; }}
#detail-header h2 {{ font-size: 16px; color: #fff; }}
#detail-close {{ cursor: pointer; font-size: 20px; color: #999; background: none; border: none; padding: 4px 8px; }}
#detail-close:hover {{ color: #fff; }}
#detail-body {{ padding: 20px; }}
.info-grid {{ display: grid; grid-template-columns: 120px 1fr; gap: 8px 16px; font-size: 13px; margin-bottom: 20px; }}
.info-label {{ color: #999; font-weight: 600; }}
.info-value {{ color: #ddd; word-break: break-word; }}
.status-badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; color: #fff; }}
h3 {{ font-size: 14px; color: #ccc; margin: 16px 0 10px; border-bottom: 1px solid #333; padding-bottom: 6px; }}
.timeline {{ display: flex; gap: 3px; flex-wrap: wrap; margin-bottom: 16px; }}
.step-block {{ padding: 4px 8px; border-radius: 4px; font-size: 10px; color: #fff; cursor: pointer; min-width: 28px; text-align: center; }}
.step-block:hover {{ opacity: 0.8; }}
.step-plan {{ background: #2196F3; }}
.step-action {{ background: #4CAF50; }}
.step-summary {{ background: #FF9800; }}
.step-detail {{ display: none; background: #0f0f23; border-radius: 6px; padding: 16px; margin-top: 10px; font-size: 12px; word-break: break-word; max-height: 500px; overflow-y: auto; line-height: 1.5; }}
.step-detail.active {{ display: block; }}
.step-detail .step-header {{ font-weight: 700; font-size: 13px; color: #fff; margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid #333; }}
.step-detail .think-box {{ background: #1a1a3e; border-left: 3px solid #7C4DFF; padding: 8px 12px; margin-bottom: 10px; border-radius: 4px; white-space: pre-wrap; color: #b0b0d0; font-size: 11px; max-height: 150px; overflow-y: auto; }}
.step-detail .tool-card {{ background: #1a1a2e; border: 1px solid #333; border-radius: 6px; padding: 10px; margin-bottom: 8px; }}
.step-detail .tool-name {{ font-weight: 700; color: #4CAF50; font-size: 12px; margin-bottom: 4px; }}
.step-detail .tool-arg {{ color: #90CAF9; font-size: 11px; margin: 2px 0; word-break: break-all; }}
.step-detail .tool-arg span {{ color: #999; }}
.step-detail .obs-box {{ background: #1a1a2e; border-left: 3px solid #FF9800; padding: 8px 12px; margin-top: 10px; border-radius: 4px; white-space: pre-wrap; color: #ccc; font-size: 11px; max-height: 200px; overflow-y: auto; }}
.step-detail .plan-content {{ white-space: pre-wrap; color: #ddd; font-size: 12px; }}
.result-box {{ background: #0f0f23; border-radius: 6px; padding: 12px; font-size: 12px; max-height: 200px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; line-height: 1.5; }}
.result-toggle {{ cursor: pointer; color: #64B5F6; font-size: 12px; margin-top: 6px; background: none; border: none; }}
.node:hover rect {{ opacity: 1; stroke-width: 3; }}
/* Gantt chart */
#gantt-container {{ padding: 20px 30px; background: #0f0f23; border-top: 1px solid #333; }}
#gantt-container h3 {{ font-size: 14px; color: #ccc; margin-bottom: 12px; border-bottom: 1px solid #333; padding-bottom: 6px; }}
.gantt-no-data {{ color: #666; font-size: 12px; font-style: italic; }}
.gantt-legend {{ display: flex; gap: 16px; font-size: 11px; margin-bottom: 10px; }}
.gantt-legend-item {{ display: flex; align-items: center; gap: 4px; color: #999; }}
.gantt-legend-color {{ width: 14px; height: 10px; border-radius: 2px; }}
.gantt-chart {{ position: relative; overflow-x: auto; }}
.gantt-lane {{ display: flex; align-items: center; margin-bottom: 4px; height: 32px; }}
.gantt-label {{ width: 140px; min-width: 140px; font-size: 11px; color: #ccc; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; padding-right: 8px; text-align: right; }}
.gantt-bar-area {{ position: relative; height: 28px; flex: 1; background: #1a1a2e; border-radius: 4px; }}
.gantt-bar {{ position: absolute; height: 12px; border-radius: 3px; opacity: 0.85; cursor: default; }}
.gantt-bar:hover {{ opacity: 1; }}
.gantt-bar-top {{ top: 2px; }}
.gantt-bar-bottom {{ top: 14px; }}
.gantt-bar-full {{ top: 4px; height: 20px; }}
.gantt-tooltip {{ display: none; position: fixed; background: #1a1a2e; border: 1px solid #555; border-radius: 6px; padding: 8px 12px; font-size: 11px; color: #ddd; z-index: 200; pointer-events: none; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }}
.gantt-tooltip.visible {{ display: block; }}
.gantt-time-axis {{ display: flex; margin-left: 140px; font-size: 9px; color: #666; margin-top: 4px; }}
.gantt-time-tick {{ position: absolute; font-size: 9px; color: #666; }}
.gantt-duration-label {{ font-size: 10px; color: #999; margin-left: 6px; white-space: nowrap; }}
/* Goal/Path mini-DAG */
.goal-dag {{ margin: 12px 0; }}
.goal-dag svg {{ display: block; margin: 0 auto; }}
.goal-dag .goal-node {{ cursor: default; }}
.goal-dag .goal-node rect {{ rx: 6; ry: 6; }}
.goal-dag .path-node {{ cursor: default; }}
.goal-dag .path-node rect {{ rx: 4; ry: 4; }}
.goal-tooltip {{ display: none; position: absolute; background: #1a1a2e; border: 1px solid #555; border-radius: 6px; padding: 10px 14px; font-size: 11px; color: #ddd; max-width: 400px; z-index: 100; word-break: break-word; line-height: 1.5; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }}
.goal-tooltip.visible {{ display: block; }}
.goal-tooltip .tt-title {{ font-weight: 700; color: #fff; margin-bottom: 4px; font-size: 12px; }}
.goal-tooltip .tt-success {{ color: #81C784; font-size: 11px; }}
.goal-tooltip .tt-status {{ display: inline-block; padding: 1px 8px; border-radius: 8px; font-size: 10px; font-weight: 600; color: #fff; margin-top: 4px; }}
</style>
</head>
<body>
<div id="header">
  <h1>{_escape(outline.get("title", "Report DAG"))}</h1>
  <div class="meta">
    <span>Topic: {_escape(outline.get("topic", ""))}</span>
    <span>Sections: {metadata.get("total_sections", len(sections))}</span>
    <span>Completed: {metadata.get("completed_sections", 0)}</span>
    <span>Failed: {metadata.get("failed_sections", 0)}</span>
    <span>Time: {metadata.get("elapsed_seconds", 0)}s</span>
    <span>Tokens: {metadata.get("total_tokens", 0):,} (in: {metadata.get("total_input_tokens", 0):,} / out: {metadata.get("total_output_tokens", 0):,})</span>
  </div>
</div>
<div id="legend">
  <div class="legend-item"><div class="legend-dot" style="background:#4CAF50"></div> Completed</div>
  <div class="legend-item"><div class="legend-dot" style="background:#F44336"></div> Failed</div>
  <div class="legend-item"><div class="legend-dot" style="background:#FF9800"></div> In Progress</div>
  <div class="legend-item"><div class="legend-dot" style="background:#2196F3"></div> Ready</div>
  <div class="legend-item"><div class="legend-dot" style="background:#9E9E9E"></div> Pending</div>
  <span style="margin-left:auto;color:#666;font-size:11px">Click a node to see details</span>
</div>
<div id="dag-container">
  <svg width="{svg_width}" height="{svg_height}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <marker id="arrow" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="10" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 3 L 0 6 z" fill="#666"/>
      </marker>
    </defs>
    {"".join(edges_svg)}
    {"".join(nodes_svg)}
  </svg>
</div>
<div id="gantt-container">
  <h3>Section Timeline (Gantt)</h3>
  <div id="gantt-chart-area"></div>
</div>
<div id="detail-panel">
  <div id="detail-header">
    <h2 id="detail-title"></h2>
    <button id="detail-close">&times;</button>
  </div>
  <div id="detail-body"></div>
</div>

<script>
const sectionData = {json.dumps(section_data_js, ensure_ascii=False)};

const statusColors = {{
  completed: "#4CAF50", failed: "#F44336", pending: "#9E9E9E",
  ready: "#2196F3", in_progress: "#FF9800"
}};

function esc(s) {{
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}}

// Current detail state
let currentSid = null;
let expandedResult = false;
let activeStep = null;

function showDetail(sid) {{
  const s = sectionData[sid];
  if (!s) return;
  currentSid = sid;
  expandedResult = false;
  activeStep = null;

  const panel = document.getElementById('detail-panel');
  const title = document.getElementById('detail-title');
  const body = document.getElementById('detail-body');

  title.textContent = s.section_id + ': ' + s.title;

  let h = '<div class="info-grid">';
  h += '<div class="info-label">Status</div><div class="info-value"><span class="status-badge" style="background:' + (statusColors[s.status]||'#999') + '">' + esc(s.status) + '</span></div>';
  h += '<div class="info-label">Depends On</div><div class="info-value">' + (s.depends_on.length ? esc(s.depends_on.join(', ')) : 'None') + '</div>';
  h += '<div class="info-label">Research Query</div><div class="info-value">' + esc(s.research_query) + '</div>';
  h += '<div class="info-label">Description</div><div class="info-value">' + esc(s.description) + '</div>';
  h += '<div class="info-label">Result Size</div><div class="info-value">' + s.result_len + ' chars</div>';
  if (s.section_duration) {{
    h += '<div class="info-label">Duration</div><div class="info-value">' + s.section_duration.toFixed(1) + 's</div>';
  }}
  var sTotalTokens = (s.total_input_tokens || 0) + (s.total_output_tokens || 0);
  if (sTotalTokens > 0) {{
    h += '<div class="info-label">Tokens</div><div class="info-value">' + sTotalTokens.toLocaleString() + ' (in: ' + (s.total_input_tokens || 0).toLocaleString() + ' / out: ' + (s.total_output_tokens || 0).toLocaleString() + ')</div>';
  }}
  h += '<div class="info-label">Retries</div><div class="info-value">' + s.retry_count + '</div>';
  if (s.error_message) {{
    h += '<div class="info-label">Error</div><div class="info-value" style="color:#F44336">' + esc(s.error_message) + '</div>';
  }}
  h += '</div>';

  // Steps timeline
  h += '<h3>Layer 2 Steps (' + s.steps.length + ' steps)</h3>';
  h += '<div class="timeline" id="timeline-bar">';
  s.steps.forEach(function(step, i) {{
    var cls = 'step-block ';
    var label = '';
    if (step.type === 'plan') {{ cls += 'step-plan'; label = 'P'; }}
    else if (step.type === 'summary') {{ cls += 'step-summary'; label = 'S'; }}
    else {{ cls += 'step-action'; label = step.num_calls || 0; }}
    h += '<div class="' + cls + '" data-step-idx="' + i + '" title="Step ' + step.idx + ': ' + step.type + '">' + label + '</div>';
  }});
  h += '</div>';
  h += '<div id="step-detail-area"></div>';

  // Research result
  h += '<h3>Research Result</h3>';
  if (s.research_result) {{
    var preview = s.research_result.substring(0, 500);
    h += '<div class="result-box" id="result-box">' + esc(preview) + (s.research_result.length > 500 ? '...' : '') + '</div>';
    if (s.research_result.length > 500) {{
      h += '<button class="result-toggle" id="result-toggle-btn">Show full result</button>';
    }}
  }} else {{
    h += '<div class="result-box" style="color:#999">No research result</div>';
  }}

  body.innerHTML = h;
  panel.style.display = 'block';
  panel.scrollIntoView({{ behavior: 'smooth' }});

  // Bind click events for timeline steps
  var timelineBar = document.getElementById('timeline-bar');
  if (timelineBar) {{
    timelineBar.addEventListener('click', function(e) {{
      var block = e.target.closest('.step-block');
      if (!block) return;
      var idx = parseInt(block.getAttribute('data-step-idx'));
      toggleStep(currentSid, idx);
    }});
  }}

  // Bind click event for result toggle
  var toggleBtn = document.getElementById('result-toggle-btn');
  if (toggleBtn) {{
    toggleBtn.addEventListener('click', function() {{
      toggleResult(currentSid);
    }});
  }}
}}

function hideDetail() {{
  document.getElementById('detail-panel').style.display = 'none';
  currentSid = null;
}}

function toggleResult(sid) {{
  var s = sectionData[sid];
  var box = document.getElementById('result-box');
  var btn = document.getElementById('result-toggle-btn');
  if (!box || !btn || !s) return;
  expandedResult = !expandedResult;
  if (expandedResult) {{
    box.textContent = s.research_result;
    box.style.maxHeight = 'none';
    btn.textContent = 'Collapse';
  }} else {{
    box.textContent = s.research_result.substring(0, 500) + (s.research_result.length > 500 ? '...' : '');
    box.style.maxHeight = '200px';
    btn.textContent = 'Show full result';
  }}
}}

function renderGoalPathDag(goals, statusMap) {{
  /* Render a mini-DAG SVG for the Goal/Path structure.
     Layout: left column = Goals (parallel, stacked vertically),
     each goal connects right to its Paths (sequential fallback chain). */
  if (!goals || goals.length === 0) return '';

  var goalW = 200, goalH = 44, pathW = 180, pathH = 36;
  var goalGapY = 16, pathGapX = 20, pathGapY = 10;
  var goalX = 30, pathStartX = goalX + goalW + 60;
  var startY = 20;

  // Status color mapping for goals
  var gStatusColors = {{
    'Completed': '#4CAF50', 'Partially Completed': '#FF9800',
    'Blocked': '#F44336', 'In Progress': '#2196F3', '': '#607D8B'
  }};
  var pStatusColors = {{
    'completed': '#4CAF50', 'partial': '#FF9800',
    'blocked': '#F44336', 'in_progress': '#2196F3', 'pending': '#607D8B'
  }};

  var nodes = [];
  var edges = [];
  var y = startY;
  var maxPathCols = 0;

  goals.forEach(function(g) {{
    var gid = g.goal_id;
    var gStatus = (statusMap && statusMap[gid]) ? statusMap[gid].status : '';
    var gColor = gStatusColors[gStatus] || gStatusColors[''];
    var gcy = y + goalH / 2;

    // Goal node
    nodes.push({{
      type: 'goal', x: goalX, y: y, w: goalW, h: goalH,
      label: 'Goal ' + gid, title: g.goal_title, color: gColor,
      status: gStatus, id: 'g' + gid
    }});

    // Paths for this goal
    var paths = g.paths || [];
    if (paths.length > maxPathCols) maxPathCols = paths.length;

    var pathTotalH = paths.length * pathH + (paths.length - 1) * pathGapY;
    var pathY = y + (goalH - pathTotalH) / 2;
    if (pathY < y - 10) pathY = y - 10;

    paths.forEach(function(p, pi) {{
      var px = pathStartX + pi * (pathW + pathGapX);
      var py = pathY + pi * (pathH + pathGapY);
      var pStatus = (statusMap && statusMap[gid] && statusMap[gid].paths && statusMap[gid].paths[p.path_id])
        ? statusMap[gid].paths[p.path_id] : 'pending';
      var pColor = pStatusColors[pStatus] || pStatusColors['pending'];

      nodes.push({{
        type: 'path', x: px, y: py, w: pathW, h: pathH,
        label: 'Path ' + p.path_id, title: p.path_title,
        success: p.success, color: pColor, status: pStatus,
        id: 'p' + p.path_id
      }});

      // Edge: goal → first path, or path[i-1] → path[i]
      if (pi === 0) {{
        edges.push({{ x1: goalX + goalW, y1: gcy, x2: px, y2: py + pathH / 2 }});
      }} else {{
        var prevPx = pathStartX + (pi - 1) * (pathW + pathGapX);
        var prevPy = pathY + (pi - 1) * (pathH + pathGapY);
        edges.push({{ x1: prevPx + pathW, y1: prevPy + pathH / 2, x2: px, y2: py + pathH / 2 }});
      }}
    }});

    var rowH = Math.max(goalH, pathTotalH);
    y += rowH + goalGapY;
  }});

  var svgW = pathStartX + maxPathCols * (pathW + pathGapX) + 40;
  var svgH = y + 10;

  var svg = '<div class="goal-dag"><svg width="' + svgW + '" height="' + svgH + '" xmlns="http://www.w3.org/2000/svg">';
  svg += '<defs><marker id="arr2" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 3 L 0 6 z" fill="#888"/></marker></defs>';

  // Edges
  edges.forEach(function(e) {{
    var cx1 = e.x1 + 20, cx2 = e.x2 - 20;
    svg += '<path d="M' + e.x1 + ',' + e.y1 + ' C' + cx1 + ',' + e.y1 + ' ' + cx2 + ',' + e.y2 + ' ' + e.x2 + ',' + e.y2 + '" fill="none" stroke="#888" stroke-width="1.5" marker-end="url(#arr2)" stroke-dasharray="4,3"/>';
  }});

  // Nodes
  nodes.forEach(function(n) {{
    var isGoal = n.type === 'goal';
    var cls = isGoal ? 'goal-node' : 'path-node';
    var fontSize = isGoal ? 12 : 10;
    var labelY = n.y + (isGoal ? 18 : 14);
    var titleY = n.y + (isGoal ? 33 : 28);
    var dispTitle = n.title || '';
    var maxChars = isGoal ? 26 : 22;
    if (dispTitle.length > maxChars) dispTitle = dispTitle.substring(0, maxChars - 1) + '…';

    svg += '<g class="' + cls + '" data-node-id="' + n.id + '">';
    svg += '<rect x="' + n.x + '" y="' + n.y + '" width="' + n.w + '" height="' + n.h + '" fill="' + n.color + '" stroke="' + n.color + '" stroke-width="1" opacity="0.85" rx="' + (isGoal ? 6 : 4) + '" ry="' + (isGoal ? 6 : 4) + '"/>';
    svg += '<text x="' + (n.x + n.w / 2) + '" y="' + labelY + '" text-anchor="middle" fill="white" font-size="' + fontSize + '" font-weight="bold" pointer-events="none">' + esc(n.label) + '</text>';
    if (isGoal) {{
      svg += '<text x="' + (n.x + n.w / 2) + '" y="' + titleY + '" text-anchor="middle" fill="rgba(255,255,255,0.8)" font-size="9" pointer-events="none">' + esc(dispTitle) + '</text>';
    }} else {{
      svg += '<text x="' + (n.x + n.w / 2) + '" y="' + titleY + '" text-anchor="middle" fill="rgba(255,255,255,0.8)" font-size="9" pointer-events="none">' + esc(dispTitle) + '</text>';
    }}
    svg += '</g>';
  }});

  svg += '</svg>';

  // Legend
  svg += '<div style="display:flex;gap:12px;margin-top:6px;font-size:10px;color:#999;padding-left:30px">';
  svg += '<span style="color:#607D8B">● Pending</span>';
  svg += '<span style="color:#2196F3">● In Progress</span>';
  svg += '<span style="color:#FF9800">● Partial</span>';
  svg += '<span style="color:#4CAF50">● Completed</span>';
  svg += '<span style="color:#F44336">● Blocked</span>';
  svg += '<span style="margin-left:auto;color:#666">Goals = parallel | Paths = sequential fallback</span>';
  svg += '</div>';

  // Tooltip area
  svg += '<div id="goal-tooltip" class="goal-tooltip"></div>';
  svg += '</div>';
  return svg;
}}

function bindGoalDagTooltips() {{
  /* Bind hover tooltips to goal-dag SVG nodes */
  var dagEl = document.querySelector('.goal-dag svg');
  if (!dagEl) return;
  var tooltip = document.getElementById('goal-tooltip');
  if (!tooltip) return;

  dagEl.addEventListener('mouseover', function(e) {{
    var node = e.target.closest('.goal-node, .path-node');
    if (!node) return;
    var nid = node.getAttribute('data-node-id');
    if (!nid || !_goalDagNodeData[nid]) return;
    var data = _goalDagNodeData[nid];
    var html = '<div class="tt-title">' + esc(data.label) + '</div>';
    html += '<div style="color:#ccc;margin-bottom:4px">' + esc(data.title) + '</div>';
    if (data.success) html += '<div class="tt-success">Success: ' + esc(data.success) + '</div>';
    if (data.status) html += '<div class="tt-status" style="background:' + (data.color || '#607D8B') + '">' + esc(data.status) + '</div>';
    tooltip.innerHTML = html;
    tooltip.classList.add('visible');
  }});

  dagEl.addEventListener('mousemove', function(e) {{
    if (!tooltip.classList.contains('visible')) return;
    var rect = dagEl.closest('.goal-dag').getBoundingClientRect();
    tooltip.style.left = (e.clientX - rect.left + 12) + 'px';
    tooltip.style.top = (e.clientY - rect.top + 12) + 'px';
  }});

  dagEl.addEventListener('mouseout', function(e) {{
    var node = e.target.closest('.goal-node, .path-node');
    if (node) {{
      tooltip.classList.remove('visible');
    }}
  }});
}}

// Temporary storage for node tooltip data
var _goalDagNodeData = {{}};

function toggleStep(sid, stepIdx) {{
  var area = document.getElementById('step-detail-area');
  var s = sectionData[sid];
  if (!s || !area) return;
  var step = s.steps[stepIdx];
  if (!step) return;

  var key = sid + '-' + stepIdx;
  if (activeStep === key) {{
    area.innerHTML = '';
    activeStep = null;
    return;
  }}
  activeStep = key;

  var typeLabels = {{plan: 'Plan', action: 'Action', summary: 'Summary'}};
  var typeColors = {{plan: '#2196F3', action: '#4CAF50', summary: '#FF9800'}};
  var h = '<div class="step-detail active">';
  var stepHeaderExtra = '';
  if (step.duration) stepHeaderExtra += ' | ' + step.duration.toFixed(1) + 's';
  if (step.llm_duration) stepHeaderExtra += ' (LLM: ' + step.llm_duration.toFixed(1) + 's)';
  var stepTokens = (step.input_tokens || 0) + (step.output_tokens || 0);
  if (stepTokens > 0) stepHeaderExtra += ' | ' + stepTokens.toLocaleString() + ' tok';
  h += '<div class="step-header" style="color:' + (typeColors[step.type]||'#fff') + '">Step ' + step.idx + ' - ' + (typeLabels[step.type]||step.type) + '<span style="color:#999;font-weight:400;font-size:11px">' + stepHeaderExtra + '</span></div>';

  // Think / reasoning
  if (step.think) {{
    h += '<div style="color:#999;font-size:11px;margin-bottom:4px">Agent Reasoning:</div>';
    h += '<div class="think-box">' + esc(step.think) + '</div>';
  }}

  if (step.type === 'plan' || step.type === 'summary') {{
    // Render Goal/Path mini-DAG if goals data exists
    var goals = step.goals || [];
    if (goals.length > 0) {{
      h += '<div style="color:#aaa;font-size:12px;font-weight:600;margin:10px 0 6px">Goal / Path DAG:</div>';

      // Build node data for tooltips
      _goalDagNodeData = {{}};
      var statusMap = step.status_map || {{}};

      var gStatusColors = {{
        'Completed': '#4CAF50', 'Partially Completed': '#FF9800',
        'Blocked': '#F44336', 'In Progress': '#2196F3', '': '#607D8B'
      }};
      var pStatusColors = {{
        'completed': '#4CAF50', 'partial': '#FF9800',
        'blocked': '#F44336', 'in_progress': '#2196F3', 'pending': '#607D8B'
      }};

      goals.forEach(function(g) {{
        var gid = g.goal_id;
        var gStatus = (statusMap[gid]) ? statusMap[gid].status : '';
        _goalDagNodeData['g' + gid] = {{
          label: 'Goal ' + gid, title: g.goal_title,
          status: gStatus, color: gStatusColors[gStatus] || gStatusColors['']
        }};
        (g.paths || []).forEach(function(p) {{
          var pStatus = (statusMap[gid] && statusMap[gid].paths && statusMap[gid].paths[p.path_id])
            ? statusMap[gid].paths[p.path_id] : 'pending';
          _goalDagNodeData['p' + p.path_id] = {{
            label: 'Path ' + p.path_id, title: p.path_title,
            success: p.success, status: pStatus,
            color: pStatusColors[pStatus] || pStatusColors['pending']
          }};
        }});
      }});

      h += renderGoalPathDag(goals, statusMap);
    }}

    // Show raw text in collapsible section
    h += '<div style="margin-top:12px">';
    h += '<div class="raw-text-toggle" style="color:#999;font-size:11px;cursor:pointer">▶ Show raw text</div>';
    h += '<div class="raw-text-content plan-content" style="display:none;margin-top:6px">' + esc(step.detail || '(empty)') + '</div>';
    h += '</div>';
  }} else if (step.type === 'action') {{
    // Tool call cards
    h += '<div style="color:#999;font-size:11px;margin-bottom:6px">Tool Calls (' + step.num_calls + '):</div>';
    (step.calls || []).forEach(function(c, i) {{
      h += '<div class="tool-card">';
      var toolDur = c.duration ? ' <span style="color:#999;font-weight:400;font-size:10px">(' + c.duration.toFixed(1) + 's)</span>' : '';
      h += '<div class="tool-name">' + (i+1) + '. ' + esc(c.tool) + toolDur + '</div>';
      if (c.goal || c.path) {{
        h += '<div style="color:#AB47BC;font-size:10px;margin-bottom:2px">' + esc((c.goal || '') + (c.path ? ' / ' + c.path : '')) + '</div>';
      }}
      if (c.tool === 'web_search') {{
        h += '<div class="tool-arg"><span>query: </span>' + esc(c.query || '') + '</div>';
      }} else if (c.tool === 'crawl_page') {{
        h += '<div class="tool-arg"><span>url: </span><a href="' + esc(c.url || '') + '" target="_blank" style="color:#64B5F6">' + esc(c.url || '') + '</a></div>';
        if (c.query) h += '<div class="tool-arg"><span>query: </span>' + esc(c.query) + '</div>';
      }} else if (c.tool === 'final_answer') {{
        h += '<div class="tool-arg"><span>answer: </span>' + esc(c.answer || '') + '</div>';
      }} else {{
        var args = c.args || {{}};
        Object.keys(args).forEach(function(k) {{
          h += '<div class="tool-arg"><span>' + esc(k) + ': </span>' + esc(args[k]) + '</div>';
        }});
      }}
      h += '</div>';
    }});

    // Observation
    if (step.obs) {{
      h += '<div style="color:#999;font-size:11px;margin-top:10px;margin-bottom:4px">Observation:</div>';
      h += '<div class="obs-box">' + esc(step.obs) + '</div>';
    }}
  }}

  h += '</div>';
  area.innerHTML = h;

  // Bind raw text toggle
  var rawToggle = area.querySelector('.raw-text-toggle');
  if (rawToggle) {{
    rawToggle.addEventListener('click', function() {{
      var content = this.nextElementSibling;
      if (content.style.display === 'none') {{
        content.style.display = 'block';
        this.textContent = '\u25bc Hide raw text';
      }} else {{
        content.style.display = 'none';
        this.textContent = '\u25b6 Show raw text';
      }}
    }});
  }}

  // Bind tooltips if we rendered a goal-dag
  if ((step.type === 'plan' || step.type === 'summary') && (step.goals || []).length > 0) {{
    bindGoalDagTooltips();
  }}
}}

function renderGanttChart() {{
  var area = document.getElementById('gantt-chart-area');
  if (!area) return;

  // Collect sections with timing data
  var lanes = [];
  Object.keys(sectionData).forEach(function(sid) {{
    var s = sectionData[sid];
    if (s.section_start_time && s.section_end_time) {{
      lanes.push(s);
    }}
  }});

  if (lanes.length === 0) {{
    area.innerHTML = '<div class="gantt-no-data">No timing data available. Run a new report to see the timeline.</div>';
    return;
  }}

  // Find global time range
  var globalStart = Infinity, globalEnd = -Infinity;
  lanes.forEach(function(s) {{
    if (s.section_start_time < globalStart) globalStart = s.section_start_time;
    if (s.section_end_time > globalEnd) globalEnd = s.section_end_time;
  }});
  var totalDuration = globalEnd - globalStart;
  if (totalDuration <= 0) totalDuration = 1;

  // Sort lanes by start time
  lanes.sort(function(a, b) {{ return a.section_start_time - b.section_start_time; }});

  var barAreaWidth = 800;

  // Legend
  var h = '<div class="gantt-legend">';
  h += '<div class="gantt-legend-item"><div class="gantt-legend-color" style="background:#42A5F5"></div>Planning LLM</div>';
  h += '<div class="gantt-legend-item"><div class="gantt-legend-color" style="background:#66BB6A"></div>Action LLM</div>';
  h += '<div class="gantt-legend-item"><div class="gantt-legend-color" style="background:#AB47BC"></div>Tool Execution</div>';
  h += '<div class="gantt-legend-item"><div class="gantt-legend-color" style="background:#FFA726"></div>Summary LLM</div>';
  h += '<div class="gantt-legend-item"><div class="gantt-legend-color" style="background:rgba(255,255,255,0.1)"></div>Section total</div>';
  h += '</div>';

  h += '<div class="gantt-chart" style="position:relative">';

  lanes.forEach(function(s) {{
    var sStart = s.section_start_time;
    var sEnd = s.section_end_time;
    var leftPct = ((sStart - globalStart) / totalDuration * 100);
    var widthPct = ((sEnd - sStart) / totalDuration * 100);
    var durText = s.section_duration ? s.section_duration.toFixed(0) + 's' : '';

    h += '<div class="gantt-lane">';
    h += '<div class="gantt-label" title="' + esc(s.title) + '">' + esc(s.section_id) + '</div>';
    h += '<div class="gantt-bar-area" style="width:' + barAreaWidth + 'px">';

    // Section background bar
    h += '<div class="gantt-bar gantt-bar-full" style="left:' + leftPct + '%;width:' + widthPct + '%;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1)" data-tip="' + esc(s.section_id + ': ' + s.title) + ' (' + durText + ')"></div>';

    // Render step bars within section
    (s.steps || []).forEach(function(step) {{
      if (!step.start_time || !step.end_time) return;
      var bLeft = ((step.start_time - globalStart) / totalDuration * 100);
      var bWidth = ((step.end_time - step.start_time) / totalDuration * 100);
      if (bWidth < 0.1) bWidth = 0.1;
      var color, cls;

      if (step.type === 'plan') {{
        color = '#42A5F5'; cls = 'gantt-bar-full';
        var tipText = 'Plan: ' + (step.duration ? step.duration.toFixed(1) + 's' : '');
        if (step.input_tokens) tipText += ' | ' + ((step.input_tokens || 0) + (step.output_tokens || 0)) + ' tok';
        h += '<div class="gantt-bar ' + cls + '" style="left:' + bLeft + '%;width:' + bWidth + '%;background:' + color + '" data-tip="' + esc(tipText) + '"></div>';
      }} else if (step.type === 'summary') {{
        color = '#FFA726'; cls = 'gantt-bar-full';
        var tipText = 'Summary: ' + (step.duration ? step.duration.toFixed(1) + 's' : '');
        if (step.input_tokens) tipText += ' | ' + ((step.input_tokens || 0) + (step.output_tokens || 0)) + ' tok';
        h += '<div class="gantt-bar ' + cls + '" style="left:' + bLeft + '%;width:' + bWidth + '%;background:' + color + '" data-tip="' + esc(tipText) + '"></div>';
      }} else if (step.type === 'action') {{
        // LLM portion (top half - green)
        if (step.llm_duration && step.start_time) {{
          var llmLeft = bLeft;
          var llmWidth = (step.llm_duration / totalDuration * 100);
          if (llmWidth < 0.1) llmWidth = 0.1;
          var llmTip = 'LLM: ' + step.llm_duration.toFixed(1) + 's';
          if (step.input_tokens) llmTip += ' | ' + ((step.input_tokens || 0) + (step.output_tokens || 0)) + ' tok';
          h += '<div class="gantt-bar gantt-bar-top" style="left:' + llmLeft + '%;width:' + llmWidth + '%;background:#66BB6A" data-tip="' + esc(llmTip) + '"></div>';
        }}
        // Tool calls (bottom half - purple, may overlap)
        (step.calls || []).forEach(function(c) {{
          if (!c.duration) return;
          // We don't have exact tool start_time in calls but can estimate from step timing
          // Tool calls happen after LLM call within the step
          // Use the step's overall bar area for tool calls
          var toolWidth = (c.duration / totalDuration * 100);
          if (toolWidth < 0.1) toolWidth = 0.1;
          var toolTip = esc(c.tool) + ': ' + c.duration.toFixed(1) + 's';
          // Position tool bars after LLM duration within the step
          var toolLeft = bLeft + (step.llm_duration ? step.llm_duration / totalDuration * 100 : 0);
          h += '<div class="gantt-bar gantt-bar-bottom" style="left:' + toolLeft + '%;width:' + toolWidth + '%;background:#AB47BC" data-tip="' + esc(toolTip) + '"></div>';
        }});
      }}
    }});

    h += '</div>';
    h += '<div class="gantt-duration-label">' + durText + '</div>';
    h += '</div>';
  }});

  // Time axis
  h += '<div style="display:flex;margin-left:140px;position:relative;height:16px;width:' + barAreaWidth + 'px">';
  var numTicks = Math.min(10, Math.ceil(totalDuration / 60));
  if (numTicks < 2) numTicks = 2;
  for (var t = 0; t <= numTicks; t++) {{
    var pct = (t / numTicks * 100);
    var timeSec = (t / numTicks * totalDuration);
    var label = timeSec >= 60 ? (timeSec / 60).toFixed(1) + 'm' : timeSec.toFixed(0) + 's';
    h += '<div class="gantt-time-tick" style="left:' + pct + '%">' + label + '</div>';
  }}
  h += '</div>';

  h += '</div>';

  // Tooltip element
  h += '<div id="gantt-tooltip" class="gantt-tooltip"></div>';

  area.innerHTML = h;

  // Bind hover tooltips
  var tooltip = document.getElementById('gantt-tooltip');
  area.addEventListener('mouseover', function(e) {{
    var bar = e.target.closest('.gantt-bar');
    if (!bar || !bar.dataset.tip) return;
    tooltip.textContent = bar.dataset.tip;
    tooltip.classList.add('visible');
  }});
  area.addEventListener('mousemove', function(e) {{
    if (!tooltip.classList.contains('visible')) return;
    tooltip.style.left = (e.clientX + 12) + 'px';
    tooltip.style.top = (e.clientY - 30) + 'px';
  }});
  area.addEventListener('mouseout', function(e) {{
    var bar = e.target.closest('.gantt-bar');
    if (bar) tooltip.classList.remove('visible');
  }});
}}

// Bind SVG node clicks via event delegation
document.addEventListener('DOMContentLoaded', function() {{
  var svg = document.querySelector('#dag-container svg');
  if (svg) {{
    svg.addEventListener('click', function(e) {{
      var node = e.target.closest('.node');
      if (node) {{
        var sid = node.getAttribute('data-sid');
        if (sid) showDetail(sid);
      }}
    }});
  }}

  // Close button
  var closeBtn = document.getElementById('detail-close');
  if (closeBtn) {{
    closeBtn.addEventListener('click', function() {{
      hideDetail();
    }});
  }}

  // Render Gantt chart
  renderGanttChart();
}});
</script>
</body>
</html>'''

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"DAG visualization saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualize report DAG from meta JSON")
    parser.add_argument("--meta_path", type=str, required=True, help="Path to _meta.json file")
    parser.add_argument("--output_path", type=str, default=None, help="Output HTML path (default: auto)")
    args = parser.parse_args()
    visualize_report_dag(args.meta_path, args.output_path)
