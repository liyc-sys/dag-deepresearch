#!/usr/bin/env python
# coding=utf-8

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


class SectionStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    section_id: str
    title: str
    description: str
    research_query: str
    depends_on: List[str] = field(default_factory=list)
    status: SectionStatus = SectionStatus.PENDING
    research_result: Optional[str] = None
    trajectory: Optional[Dict] = None
    error_message: Optional[str] = None
    retry_count: int = 0

    def dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "description": self.description,
            "research_query": self.research_query,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "research_result": self.research_result,
            "trajectory": self.trajectory,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
        }


@dataclass
class ReportOutline:
    topic: str
    title: str
    sections: List[ReportSection] = field(default_factory=list)

    def get_ready_sections(self) -> List[ReportSection]:
        """Return all PENDING sections whose dependencies are all COMPLETED, and mark them READY."""
        completed_ids = {s.section_id for s in self.sections if s.status == SectionStatus.COMPLETED}
        ready = []
        for section in self.sections:
            if section.status != SectionStatus.PENDING:
                continue
            if all(dep_id in completed_ids for dep_id in section.depends_on):
                section.status = SectionStatus.READY
                ready.append(section)
        return ready

    def all_completed(self) -> bool:
        """Check if all sections are COMPLETED or FAILED."""
        return all(s.status in (SectionStatus.COMPLETED, SectionStatus.FAILED) for s in self.sections)

    def get_completed_context(self, section_ids: List[str], max_chars_per_section: int = 2000) -> str:
        """Get truncated research results from specified completed sections."""
        if not section_ids:
            return ""
        parts = []
        for section in self.sections:
            if section.section_id in section_ids and section.status == SectionStatus.COMPLETED and section.research_result:
                result = section.research_result
                if len(result) > max_chars_per_section:
                    result = result[:max_chars_per_section] + "... [truncated]"
                parts.append(f"### {section.title}\n{result}")
        return "\n\n".join(parts)

    def validate_dag(self) -> bool:
        """Validate that the DAG has no cycles and all depends_on references are valid."""
        section_ids = {s.section_id for s in self.sections}

        # Check all references are valid
        for section in self.sections:
            for dep_id in section.depends_on:
                if dep_id not in section_ids:
                    return False

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {s.section_id: WHITE for s in self.sections}

        # Build adjacency list: dep -> dependent (edges from dependency to dependent)
        adj = {s.section_id: [] for s in self.sections}
        for section in self.sections:
            for dep_id in section.depends_on:
                adj[dep_id].append(section.section_id)

        def has_cycle(node: str) -> bool:
            color[node] = GRAY
            for neighbor in adj[node]:
                if color[neighbor] == GRAY:
                    return True
                if color[neighbor] == WHITE and has_cycle(neighbor):
                    return True
            color[node] = BLACK
            return False

        for sid in section_ids:
            if color[sid] == WHITE:
                if has_cycle(sid):
                    return False

        return True

    def dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "title": self.title,
            "sections": [s.dict() for s in self.sections],
        }
