#!/usr/bin/env python
# coding=utf-8

import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from typing import Dict, Optional

import json_repair
import yaml
from jinja2 import StrictUndefined, Template

from .report_dag import ReportOutline, ReportSection, SectionStatus
from .models import OpenAIServerModel

logger = logging.getLogger(__name__)

CONTEXT_THRESHOLD = 60000


def _render_template(template_str: str, variables: dict) -> str:
    compiled = Template(template_str, undefined=StrictUndefined)
    return compiled.render(**variables)


def _load_report_prompts() -> dict:
    prompts_path = os.path.join(
        os.path.dirname(__file__), "prompts", "report", "report_prompts.yaml"
    )
    with open(prompts_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class ReportOrchestrator:
    def __init__(
        self,
        model: OpenAIServerModel,
        max_section_steps: int = 20,
        summary_interval: int = 6,
        section_concurrency: int = 5,
        max_section_retries: int = 2,
        prompts_type: str = "default",
    ):
        self.model = model
        self.max_section_steps = max_section_steps
        self.summary_interval = summary_interval
        self.section_concurrency = section_concurrency
        self.max_section_retries = max_section_retries
        self.prompts_type = prompts_type
        self.prompts = _load_report_prompts()

    def _call_model(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": user_prompt}],
            },
        ]
        response = self.model(messages)
        return response.content

    def plan_report(self, topic: str) -> ReportOutline:
        """Generate a report outline DAG from the topic using LLM."""
        planning = self.prompts["report_planning"]
        system_prompt = planning["system_prompt"]
        task_input = _render_template(planning["task_input"], {"topic": topic})

        last_error = None
        for attempt in range(3):
            try:
                raw = self._call_model(system_prompt, task_input)
                parsed = json_repair.loads(raw)
                if isinstance(parsed, str):
                    raise ValueError(f"LLM returned non-JSON string: {parsed[:200]}")

                report_title = parsed.get("report_title", topic)
                sections = []
                for s in parsed["sections"]:
                    sections.append(
                        ReportSection(
                            section_id=s["section_id"],
                            title=s["title"],
                            description=s["description"],
                            research_query=s["research_query"],
                            depends_on=s.get("depends_on", []),
                        )
                    )

                outline = ReportOutline(
                    topic=topic, title=report_title, sections=sections
                )

                if not outline.validate_dag():
                    raise ValueError("Invalid DAG: cycle detected or invalid dependency reference")

                logger.info(
                    f"Report outline planned: '{report_title}' with {len(sections)} sections"
                )
                return outline

            except Exception as e:
                last_error = e
                logger.warning(f"Plan attempt {attempt + 1} failed: {e}")

        raise RuntimeError(f"Failed to plan report after 3 attempts: {last_error}")

    def _research_section(
        self, section: ReportSection, dependency_context: str, topic: str
    ) -> ReportSection:
        """Research a single section using a fresh SearchAgent instance (Layer 2)."""
        from base_agent import SearchAgent

        research_tmpl = self.prompts["section_research"]["context_prefix"]
        task_string = _render_template(
            research_tmpl,
            {
                "topic": topic,
                "title": section.title,
                "description": section.description,
                "research_query": section.research_query,
                "dependency_context": dependency_context,
            },
        )

        logger.info(f"Starting research for section '{section.title}' ({section.section_id})")

        search_agent = SearchAgent(
            model=self.model,
            summary_interval=self.summary_interval,
            prompts_type=self.prompts_type,
            max_steps=self.max_section_steps,
        )

        result = search_agent(task_string)

        if "error" in result and "agent_result" not in result:
            raise RuntimeError(f"SearchAgent failed: {result['error']}")

        section.research_result = result.get("agent_result", "")
        section.trajectory = result.get("agent_trajectory")

        logger.info(f"Completed research for section '{section.title}' ({section.section_id})")
        return section

    def execute_report(self, outline: ReportOutline) -> ReportOutline:
        """Execute all sections with immediate scheduling using DAG dependencies."""
        with ThreadPoolExecutor(max_workers=self.section_concurrency) as executor:
            futures = {}

            def submit_ready_sections():
                for section in outline.get_ready_sections():
                    section.status = SectionStatus.IN_PROGRESS
                    dep_context = outline.get_completed_context(section.depends_on)
                    future = executor.submit(
                        self._research_section, section, dep_context, outline.topic
                    )
                    futures[future] = section

            # Initial submission
            submit_ready_sections()

            while futures:
                done, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)

                for future in done:
                    section = futures.pop(future)
                    try:
                        result = future.result()
                        section.research_result = result.research_result
                        section.trajectory = result.trajectory
                        section.status = SectionStatus.COMPLETED
                        logger.info(
                            f"Section '{section.title}' ({section.section_id}) completed"
                        )
                    except Exception as e:
                        section.retry_count += 1
                        if section.retry_count <= self.max_section_retries:
                            section.status = SectionStatus.PENDING
                            section.error_message = str(e)
                            logger.warning(
                                f"Section '{section.title}' failed (attempt {section.retry_count}), will retry: {e}"
                            )
                        else:
                            section.status = SectionStatus.FAILED
                            section.error_message = f"Failed after {self.max_section_retries} retries: {e}"
                            logger.error(
                                f"Section '{section.title}' permanently failed: {e}"
                            )

                    # Check for newly ready sections after each completion
                    submit_ready_sections()

            # Handle deadlocked sections (dependencies that failed)
            pending = [
                s
                for s in outline.sections
                if s.status in (SectionStatus.PENDING, SectionStatus.READY)
            ]
            if pending:
                for s in pending:
                    s.status = SectionStatus.FAILED
                    s.error_message = "Deadlock: dependency never completed"
                    logger.error(f"Section '{s.title}' deadlocked")

        return outline

    def _compress_section(self, section: ReportSection) -> str:
        """Compress a section's research result to save context space."""
        compress_tmpl = self.prompts["report_synthesis"]["compress_section"]
        prompt = _render_template(
            compress_tmpl,
            {
                "title": section.title,
                "research_result": section.research_result,
            },
        )
        system_prompt = "You are a concise summarizer. Compress the given research findings while preserving key facts and source URLs."
        return self._call_model(system_prompt, prompt)

    def _final_synthesis(self, outline: ReportOutline) -> str:
        """Synthesize all section results into the final report."""
        synthesis = self.prompts["report_synthesis"]
        system_prompt = synthesis["system_prompt"]

        sections_data = []
        for s in outline.sections:
            sections_data.append(
                {
                    "title": s.title,
                    "description": s.description,
                    "status": s.status.value,
                    "research_result": s.research_result,
                    "error_message": s.error_message,
                }
            )

        task_input = _render_template(
            synthesis["task_input"],
            {
                "topic": outline.topic,
                "title": outline.title,
                "sections": sections_data,
            },
        )

        return self._call_model(system_prompt, task_input)

    def synthesize_report(self, outline: ReportOutline) -> str:
        """Adaptively synthesize the report, compressing if needed."""
        total_chars = sum(len(s.research_result or "") for s in outline.sections)

        if total_chars > CONTEXT_THRESHOLD:
            logger.info(
                f"Total research chars ({total_chars}) exceeds threshold ({CONTEXT_THRESHOLD}), compressing..."
            )
            for section in outline.sections:
                if section.research_result and len(section.research_result) > 3000:
                    section.research_result = self._compress_section(section)

        last_error = None
        for attempt in range(3):
            try:
                report = self._final_synthesis(outline)
                logger.info("Report synthesis completed")
                return report
            except Exception as e:
                last_error = e
                logger.warning(f"Synthesis attempt {attempt + 1} failed: {e}")

        # Fallback: concatenate raw section results
        logger.error(f"Synthesis failed after 3 attempts: {last_error}. Using fallback concatenation.")
        parts = [f"# {outline.title}\n"]
        for i, section in enumerate(outline.sections, 1):
            parts.append(f"## {i}. {section.title}\n")
            if section.research_result:
                parts.append(section.research_result)
            elif section.error_message:
                parts.append(f"*Research failed: {section.error_message}*")
            else:
                parts.append("*No research results available.*")
            parts.append("")
        return "\n\n".join(parts)

    def generate_report(self, topic: str) -> Dict:
        """Main entry: plan, research, and synthesize a deep research report."""
        start_time = time.time()

        logger.info(f"Starting report generation for topic: {topic}")

        # Phase 1: Plan
        outline = self.plan_report(topic)

        # Phase 2: Research
        outline = self.execute_report(outline)

        # Phase 3: Synthesize
        report = self.synthesize_report(outline)

        elapsed = time.time() - start_time
        completed = sum(1 for s in outline.sections if s.status == SectionStatus.COMPLETED)
        failed = sum(1 for s in outline.sections if s.status == SectionStatus.FAILED)

        metadata = {
            "topic": topic,
            "total_sections": len(outline.sections),
            "completed_sections": completed,
            "failed_sections": failed,
            "elapsed_seconds": round(elapsed, 2),
        }

        logger.info(
            f"Report generated: {completed}/{len(outline.sections)} sections completed, "
            f"{failed} failed, {elapsed:.1f}s elapsed"
        )

        return {
            "topic": topic,
            "outline": outline.dict(),
            "report": report,
            "metadata": metadata,
        }
