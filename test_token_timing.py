#!/usr/bin/env python
# coding=utf-8
"""
Tests for Token统计 + 耗时追踪 + Gantt可视化 feature.

Covers:
  1. ChatMessage token fields
  2. memory.py dataclass extensions (ToolCall, ActionStep, PlanningStep, SummaryStep)
  3. base_agent.py capture_trajectory serialization
  4. ReportSection timing/token fields
  5. visualize_dag.py Gantt chart rendering + graceful degradation
"""

import json
import os
import sys
import tempfile
import time

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from FlashOAgents.models import ChatMessage
from FlashOAgents.memory import ToolCall, ActionStep, PlanningStep, SummaryStep, TaskStep
from FlashOAgents.report_dag import ReportSection, SectionStatus
from visualize_dag import visualize_report_dag


# ──────────────────────────────────────────────
# 1. ChatMessage token fields
# ──────────────────────────────────────────────
class TestChatMessageTokenFields:
    def test_default_none(self):
        msg = ChatMessage(role="assistant", content="hello")
        assert msg.input_token_count is None
        assert msg.output_token_count is None

    def test_set_token_counts(self):
        msg = ChatMessage(role="assistant", content="hello",
                          input_token_count=100, output_token_count=50)
        assert msg.input_token_count == 100
        assert msg.output_token_count == 50

    def test_from_dict_preserves_extra_fields(self):
        """from_dict should not crash even though token fields aren't in the dict."""
        msg = ChatMessage.from_dict({"role": "assistant", "content": "hi"})
        assert msg.input_token_count is None
        assert msg.output_token_count is None

    def test_token_fields_independent_per_instance(self):
        """Thread-safety: each ChatMessage has its own token fields."""
        m1 = ChatMessage(role="assistant", content="a", input_token_count=10, output_token_count=20)
        m2 = ChatMessage(role="assistant", content="b", input_token_count=30, output_token_count=40)
        assert m1.input_token_count == 10
        assert m2.input_token_count == 30


# ──────────────────────────────────────────────
# 2. ToolCall timing fields
# ──────────────────────────────────────────────
class TestToolCallTiming:
    def test_default_none(self):
        tc = ToolCall(name="web_search", arguments={"query": "test"}, id="tc1")
        assert tc.start_time is None
        assert tc.end_time is None
        assert tc.duration is None

    def test_set_timing(self):
        tc = ToolCall(name="web_search", arguments={"query": "test"}, id="tc1",
                      start_time=1000.0, end_time=1005.0, duration=5.0)
        assert tc.duration == 5.0

    def test_dict_includes_timing(self):
        tc = ToolCall(name="crawl_page", arguments={"url": "http://x.com"}, id="tc2",
                      start_time=100.0, end_time=103.5, duration=3.5)
        d = tc.dict()
        assert d["start_time"] == 100.0
        assert d["end_time"] == 103.5
        assert d["duration"] == 3.5
        assert d["name"] == "crawl_page"

    def test_dict_timing_none_when_unset(self):
        tc = ToolCall(name="web_search", arguments={}, id="tc3")
        d = tc.dict()
        assert d["start_time"] is None
        assert d["duration"] is None


# ──────────────────────────────────────────────
# 3. ActionStep token + LLM timing fields
# ──────────────────────────────────────────────
class TestActionStepTokenTiming:
    def test_defaults_none(self):
        step = ActionStep()
        assert step.input_tokens is None
        assert step.output_tokens is None
        assert step.llm_start_time is None
        assert step.llm_end_time is None
        assert step.llm_duration is None

    def test_set_values(self):
        step = ActionStep(
            input_tokens=500, output_tokens=200,
            llm_start_time=1000.0, llm_end_time=1003.0, llm_duration=3.0,
        )
        assert step.input_tokens == 500
        assert step.llm_duration == 3.0

    def test_dict_includes_new_fields(self):
        step = ActionStep(
            input_tokens=500, output_tokens=200,
            llm_start_time=1000.0, llm_end_time=1003.0, llm_duration=3.0,
        )
        d = step.dict()
        assert d["input_tokens"] == 500
        assert d["output_tokens"] == 200
        assert d["llm_start_time"] == 1000.0
        assert d["llm_end_time"] == 1003.0
        assert d["llm_duration"] == 3.0

    def test_dict_with_timed_tool_calls(self):
        tc = ToolCall(name="web_search", arguments={}, id="t1",
                      start_time=100.0, end_time=102.0, duration=2.0)
        step = ActionStep(tool_calls=[tc], input_tokens=100, output_tokens=50)
        d = step.dict()
        assert d["tool_calls"][0]["duration"] == 2.0
        assert d["input_tokens"] == 100


# ──────────────────────────────────────────────
# 4. PlanningStep timing/token fields
# ──────────────────────────────────────────────
class TestPlanningStepTiming:
    def test_defaults_none(self):
        step = PlanningStep(
            model_input_messages=[], plan="do stuff",
            plan_think="", plan_reasoning="",
        )
        assert step.start_time is None
        assert step.duration is None
        assert step.input_tokens is None

    def test_with_timing(self):
        step = PlanningStep(
            model_input_messages=[], plan="plan",
            plan_think="think", plan_reasoning="reason",
            start_time=100.0, end_time=105.0, duration=5.0,
            input_tokens=800, output_tokens=300,
        )
        assert step.duration == 5.0
        assert step.input_tokens == 800
        assert step.output_tokens == 300


# ──────────────────────────────────────────────
# 5. SummaryStep timing/token fields
# ──────────────────────────────────────────────
class TestSummaryStepTiming:
    def test_defaults_none(self):
        step = SummaryStep(
            model_input_messages=[], summary="summary text",
            summary_reasoning="reason",
        )
        assert step.start_time is None
        assert step.input_tokens is None

    def test_with_timing(self):
        step = SummaryStep(
            model_input_messages=[], summary="summary",
            summary_reasoning="reason",
            start_time=200.0, end_time=208.0, duration=8.0,
            input_tokens=1200, output_tokens=400,
        )
        assert step.duration == 8.0
        assert step.output_tokens == 400


# ──────────────────────────────────────────────
# 6. capture_trajectory serialization
# ──────────────────────────────────────────────
class TestCaptureTrajectory:
    """Test that capture_trajectory includes timing/token fields."""

    def _make_agent_stub(self):
        """Build a minimal object that mimics BaseAgent with an agent_fn.memory."""
        from FlashOAgents.agents import ToolCallingAgent

        class FakeMemory:
            def __init__(self):
                self.steps = []

        class FakeAgentFn:
            def __init__(self):
                self.memory = FakeMemory()

        # We can't easily instantiate ToolCallingAgent, so we hack isinstance check
        # by making agent_fn look like one
        class AgentStub:
            def __init__(self):
                self.agent_fn = FakeAgentFn()
                # Patch isinstance check: set __class__
                self.agent_fn.__class__ = ToolCallingAgent

            def capture_trajectory(self):
                """Copy of BaseAgent.capture_trajectory logic."""
                trajectory = []
                for step in self.agent_fn.memory.steps:
                    if isinstance(step, TaskStep):
                        continue
                    elif isinstance(step, PlanningStep):
                        traj = {"name": "plan", "value": step.plan,
                                "think": step.plan_think, "cot_think": step.plan_reasoning,
                                "start_time": step.start_time, "end_time": step.end_time,
                                "duration": step.duration,
                                "input_tokens": step.input_tokens, "output_tokens": step.output_tokens}
                        trajectory.append(traj)
                    elif isinstance(step, SummaryStep):
                        traj = {"name": "summary", "value": step.summary,
                                "cot_think": step.summary_reasoning,
                                "start_time": step.start_time, "end_time": step.end_time,
                                "duration": step.duration,
                                "input_tokens": step.input_tokens, "output_tokens": step.output_tokens}
                        trajectory.append(traj)
                    elif isinstance(step, ActionStep):
                        safe_tool_calls = step.tool_calls if step.tool_calls is not None else []
                        traj = {"name": "action",
                                "tool_calls": [st.dict() for st in safe_tool_calls],
                                "obs": step.observations,
                                "think": step.action_think, "cot_think": step.action_reasoning,
                                "start_time": step.start_time, "end_time": step.end_time,
                                "duration": step.duration,
                                "input_tokens": step.input_tokens, "output_tokens": step.output_tokens,
                                "llm_start_time": step.llm_start_time, "llm_end_time": step.llm_end_time,
                                "llm_duration": step.llm_duration}
                        trajectory.append(traj)
                return {"agent_trajectory": trajectory}

        return AgentStub()

    def test_planning_step_serialization(self):
        agent = self._make_agent_stub()
        agent.agent_fn.memory.steps.append(PlanningStep(
            model_input_messages=[], plan="plan", plan_think="", plan_reasoning="r",
            start_time=100.0, end_time=105.0, duration=5.0,
            input_tokens=800, output_tokens=300,
        ))
        result = agent.capture_trajectory()
        traj = result["agent_trajectory"]
        assert len(traj) == 1
        assert traj[0]["name"] == "plan"
        assert traj[0]["duration"] == 5.0
        assert traj[0]["input_tokens"] == 800

    def test_action_step_serialization(self):
        agent = self._make_agent_stub()
        tc = ToolCall(name="web_search", arguments={"query": "test"}, id="t1",
                      start_time=100.0, end_time=102.0, duration=2.0)
        agent.agent_fn.memory.steps.append(ActionStep(
            tool_calls=[tc], observations="result",
            action_think="thinking", action_reasoning="reason",
            start_time=99.0, end_time=103.0, duration=4.0,
            input_tokens=500, output_tokens=200,
            llm_start_time=99.0, llm_end_time=100.0, llm_duration=1.0,
        ))
        result = agent.capture_trajectory()
        traj = result["agent_trajectory"]
        assert len(traj) == 1
        assert traj[0]["llm_duration"] == 1.0
        assert traj[0]["tool_calls"][0]["duration"] == 2.0

    def test_summary_step_serialization(self):
        agent = self._make_agent_stub()
        agent.agent_fn.memory.steps.append(SummaryStep(
            model_input_messages=[], summary="s", summary_reasoning="r",
            start_time=200.0, end_time=206.0, duration=6.0,
            input_tokens=1000, output_tokens=400,
        ))
        result = agent.capture_trajectory()
        traj = result["agent_trajectory"]
        assert traj[0]["input_tokens"] == 1000
        assert traj[0]["duration"] == 6.0

    def test_task_step_skipped(self):
        agent = self._make_agent_stub()
        agent.agent_fn.memory.steps.append(TaskStep(task="hello"))
        result = agent.capture_trajectory()
        assert len(result["agent_trajectory"]) == 0


# ──────────────────────────────────────────────
# 7. ReportSection timing/token fields
# ──────────────────────────────────────────────
class TestReportSection:
    def test_default_none(self):
        sec = ReportSection(
            section_id="s1", title="Intro",
            description="desc", research_query="query",
        )
        assert sec.section_start_time is None
        assert sec.section_duration is None
        assert sec.total_input_tokens is None

    def test_with_timing(self):
        sec = ReportSection(
            section_id="s1", title="Intro",
            description="desc", research_query="query",
            section_start_time=1000.0, section_end_time=1060.0, section_duration=60.0,
            total_input_tokens=5000, total_output_tokens=2000,
        )
        assert sec.section_duration == 60.0
        assert sec.total_input_tokens == 5000

    def test_dict_includes_timing(self):
        sec = ReportSection(
            section_id="s1", title="T", description="D", research_query="Q",
            section_start_time=100.0, section_end_time=200.0, section_duration=100.0,
            total_input_tokens=3000, total_output_tokens=1000,
        )
        d = sec.dict()
        assert d["section_start_time"] == 100.0
        assert d["section_end_time"] == 200.0
        assert d["section_duration"] == 100.0
        assert d["total_input_tokens"] == 3000
        assert d["total_output_tokens"] == 1000


# ──────────────────────────────────────────────
# 8. visualize_dag.py — old data graceful degradation
# ──────────────────────────────────────────────
class TestVisualizeDagGracefulDegradation:
    """Test with meta.json that has no timing/token data (old format)."""

    def _make_old_meta(self):
        return {
            "outline": {
                "topic": "Test Topic",
                "title": "Test Report",
                "sections": [
                    {
                        "section_id": "s1",
                        "title": "Section 1",
                        "description": "desc",
                        "research_query": "query",
                        "depends_on": [],
                        "status": "completed",
                        "research_result": "Some result text",
                        "trajectory": [
                            {"name": "plan", "value": "plan text", "think": "t", "cot_think": "c"},
                            {"name": "action", "tool_calls": [{"name": "web_search", "arguments": {"query": "q"}}], "obs": "obs", "think": "t", "cot_think": "c"},
                        ],
                        "error_message": None,
                        "retry_count": 0,
                        # No timing/token fields
                    },
                    {
                        "section_id": "s2",
                        "title": "Section 2",
                        "description": "desc2",
                        "research_query": "query2",
                        "depends_on": ["s1"],
                        "status": "completed",
                        "research_result": "Result 2",
                        "trajectory": [],
                        "error_message": None,
                        "retry_count": 0,
                    },
                ],
            },
            "metadata": {
                "topic": "Test Topic",
                "total_sections": 2,
                "completed_sections": 2,
                "failed_sections": 0,
                "elapsed_seconds": 120.5,
                # No token fields
            },
        }

    def test_old_meta_renders_without_error(self):
        meta = self._make_old_meta()
        with tempfile.NamedTemporaryFile(mode="w", suffix="_meta.json", delete=False) as f:
            json.dump(meta, f)
            meta_path = f.name
        try:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as out_f:
                output_path = out_f.name
            visualize_report_dag(meta_path, output_path)
            html = open(output_path, "r", encoding="utf-8").read()
            assert len(html) > 100
        finally:
            os.unlink(meta_path)
            os.unlink(output_path)

    def test_old_meta_shows_no_timing_data_message(self):
        meta = self._make_old_meta()
        with tempfile.NamedTemporaryFile(mode="w", suffix="_meta.json", delete=False) as f:
            json.dump(meta, f)
            meta_path = f.name
        try:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as out_f:
                output_path = out_f.name
            visualize_report_dag(meta_path, output_path)
            html = open(output_path, "r", encoding="utf-8").read()
            # Gantt chart should show graceful degradation message
            assert "No timing data" in html
        finally:
            os.unlink(meta_path)
            os.unlink(output_path)

    def test_old_meta_tokens_show_zero(self):
        meta = self._make_old_meta()
        with tempfile.NamedTemporaryFile(mode="w", suffix="_meta.json", delete=False) as f:
            json.dump(meta, f)
            meta_path = f.name
        try:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as out_f:
                output_path = out_f.name
            visualize_report_dag(meta_path, output_path)
            html = open(output_path, "r", encoding="utf-8").read()
            assert "Tokens: 0" in html
        finally:
            os.unlink(meta_path)
            os.unlink(output_path)


# ──────────────────────────────────────────────
# 9. visualize_dag.py — new data with timing/tokens
# ──────────────────────────────────────────────
class TestVisualizeDagWithTimingData:
    """Test with meta.json that has full timing/token data (new format)."""

    def _make_new_meta(self):
        base_time = 1700000000.0
        return {
            "outline": {
                "topic": "Test Topic",
                "title": "Test Report With Timing",
                "sections": [
                    {
                        "section_id": "s1",
                        "title": "Section 1",
                        "description": "desc",
                        "research_query": "query",
                        "depends_on": [],
                        "status": "completed",
                        "research_result": "Result 1",
                        "trajectory": [
                            {
                                "name": "plan", "value": "plan text", "think": "t", "cot_think": "c",
                                "start_time": base_time, "end_time": base_time + 5.0, "duration": 5.0,
                                "input_tokens": 800, "output_tokens": 300,
                            },
                            {
                                "name": "action",
                                "tool_calls": [
                                    {"name": "web_search", "arguments": {"query": "q"},
                                     "start_time": base_time + 6.0, "end_time": base_time + 8.0, "duration": 2.0},
                                ],
                                "obs": "search results", "think": "t", "cot_think": "c",
                                "start_time": base_time + 5.0, "end_time": base_time + 10.0, "duration": 5.0,
                                "input_tokens": 1000, "output_tokens": 500,
                                "llm_start_time": base_time + 5.0, "llm_end_time": base_time + 6.0,
                                "llm_duration": 1.0,
                            },
                            {
                                "name": "summary", "value": "summary text", "cot_think": "c",
                                "start_time": base_time + 10.0, "end_time": base_time + 15.0, "duration": 5.0,
                                "input_tokens": 1200, "output_tokens": 400,
                            },
                        ],
                        "error_message": None,
                        "retry_count": 0,
                        "section_start_time": base_time,
                        "section_end_time": base_time + 15.0,
                        "section_duration": 15.0,
                        "total_input_tokens": 3000,
                        "total_output_tokens": 1200,
                    },
                    {
                        "section_id": "s2",
                        "title": "Section 2 (parallel)",
                        "description": "desc2",
                        "research_query": "query2",
                        "depends_on": [],
                        "status": "completed",
                        "research_result": "Result 2",
                        "trajectory": [
                            {
                                "name": "plan", "value": "p2", "think": "t", "cot_think": "c",
                                "start_time": base_time + 1.0, "end_time": base_time + 4.0, "duration": 3.0,
                                "input_tokens": 600, "output_tokens": 200,
                            },
                        ],
                        "error_message": None,
                        "retry_count": 0,
                        "section_start_time": base_time + 1.0,
                        "section_end_time": base_time + 20.0,
                        "section_duration": 19.0,
                        "total_input_tokens": 600,
                        "total_output_tokens": 200,
                    },
                ],
            },
            "metadata": {
                "topic": "Test Topic",
                "total_sections": 2,
                "completed_sections": 2,
                "failed_sections": 0,
                "elapsed_seconds": 20.0,
                "total_input_tokens": 3600,
                "total_output_tokens": 1400,
                "total_tokens": 5000,
            },
        }

    def test_new_meta_renders_without_error(self):
        meta = self._make_new_meta()
        with tempfile.NamedTemporaryFile(mode="w", suffix="_meta.json", delete=False) as f:
            json.dump(meta, f)
            meta_path = f.name
        try:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as out_f:
                output_path = out_f.name
            visualize_report_dag(meta_path, output_path)
            html = open(output_path, "r", encoding="utf-8").read()
            assert len(html) > 100
        finally:
            os.unlink(meta_path)
            os.unlink(output_path)

    def test_header_shows_token_count(self):
        meta = self._make_new_meta()
        with tempfile.NamedTemporaryFile(mode="w", suffix="_meta.json", delete=False) as f:
            json.dump(meta, f)
            meta_path = f.name
        try:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as out_f:
                output_path = out_f.name
            visualize_report_dag(meta_path, output_path)
            html = open(output_path, "r", encoding="utf-8").read()
            assert "Tokens: 5,000" in html
            assert "in: 3,600" in html
            assert "out: 1,400" in html
        finally:
            os.unlink(meta_path)
            os.unlink(output_path)

    def test_node_shows_token_and_duration(self):
        meta = self._make_new_meta()
        with tempfile.NamedTemporaryFile(mode="w", suffix="_meta.json", delete=False) as f:
            json.dump(meta, f)
            meta_path = f.name
        try:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as out_f:
                output_path = out_f.name
            visualize_report_dag(meta_path, output_path)
            html = open(output_path, "r", encoding="utf-8").read()
            # s1: 3 steps, 4200 tokens, 15s
            assert "4,200 tok" in html
            assert "15s" in html
        finally:
            os.unlink(meta_path)
            os.unlink(output_path)

    def test_gantt_has_section_lanes(self):
        """With timing data, section_data_js should carry timing so Gantt JS can render lanes."""
        meta = self._make_new_meta()
        with tempfile.NamedTemporaryFile(mode="w", suffix="_meta.json", delete=False) as f:
            json.dump(meta, f)
            meta_path = f.name
        try:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as out_f:
                output_path = out_f.name
            visualize_report_dag(meta_path, output_path)
            html = open(output_path, "r", encoding="utf-8").read()
            # Extract sectionData JSON and verify timing data is present for Gantt
            start_marker = "const sectionData = "
            start_idx = html.index(start_marker) + len(start_marker)
            end_idx = html.index(";\n", start_idx)
            section_data = json.loads(html[start_idx:end_idx])
            # Both sections have timing, so Gantt JS will render lanes (not no-data)
            assert section_data["s1"]["section_start_time"] is not None
            assert section_data["s2"]["section_start_time"] is not None
            assert section_data["s1"]["section_duration"] == 15.0
            assert section_data["s2"]["section_duration"] == 19.0
        finally:
            os.unlink(meta_path)
            os.unlink(output_path)

    def test_section_data_js_has_step_timing(self):
        """section_data_js should include per-step timing and token fields."""
        meta = self._make_new_meta()
        with tempfile.NamedTemporaryFile(mode="w", suffix="_meta.json", delete=False) as f:
            json.dump(meta, f)
            meta_path = f.name
        try:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as out_f:
                output_path = out_f.name
            visualize_report_dag(meta_path, output_path)
            html = open(output_path, "r", encoding="utf-8").read()
            # Extract sectionData JSON from HTML
            start_marker = "const sectionData = "
            start_idx = html.index(start_marker) + len(start_marker)
            # Find the closing semicolon
            end_idx = html.index(";\n", start_idx)
            section_data = json.loads(html[start_idx:end_idx])

            # Check s1 section-level fields
            s1 = section_data["s1"]
            assert s1["section_duration"] == 15.0
            assert s1["total_input_tokens"] == 3000
            assert s1["total_output_tokens"] == 1200

            # Check s1 plan step timing
            plan_step = s1["steps"][0]
            assert plan_step["type"] == "plan"
            assert plan_step["duration"] == 5.0
            assert plan_step["input_tokens"] == 800
            assert plan_step["output_tokens"] == 300

            # Check s1 action step with LLM duration and tool duration
            action_step = s1["steps"][1]
            assert action_step["type"] == "action"
            assert action_step["llm_duration"] == 1.0
            assert action_step["input_tokens"] == 1000
            assert action_step["calls"][0]["duration"] == 2.0

            # Check s1 summary step
            summary_step = s1["steps"][2]
            assert summary_step["type"] == "summary"
            assert summary_step["duration"] == 5.0
        finally:
            os.unlink(meta_path)
            os.unlink(output_path)

    def test_gantt_container_present(self):
        meta = self._make_new_meta()
        with tempfile.NamedTemporaryFile(mode="w", suffix="_meta.json", delete=False) as f:
            json.dump(meta, f)
            meta_path = f.name
        try:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as out_f:
                output_path = out_f.name
            visualize_report_dag(meta_path, output_path)
            html = open(output_path, "r", encoding="utf-8").read()
            assert 'id="gantt-container"' in html
            assert 'id="gantt-chart-area"' in html
            assert "Section Timeline (Gantt)" in html
            assert "renderGanttChart" in html
        finally:
            os.unlink(meta_path)
            os.unlink(output_path)


# ──────────────────────────────────────────────
# 10. Existing meta.json compatibility
# ──────────────────────────────────────────────
class TestExistingMetaJson:
    """Test against the actual existing meta.json file if it exists."""

    META_PATH = os.path.join(PROJECT_ROOT, "output", "llm_science_report_meta.json")

    @pytest.mark.skipif(
        not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "output", "llm_science_report_meta.json")),
        reason="Existing meta.json not found"
    )
    def test_existing_meta_renders(self):
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as out_f:
            output_path = out_f.name
        try:
            visualize_report_dag(self.META_PATH, output_path)
            html = open(output_path, "r", encoding="utf-8").read()
            assert len(html) > 1000
            assert 'id="gantt-container"' in html
            # Old data: should show "No timing data" via JS
            assert "No timing data" in html
        finally:
            os.unlink(output_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
