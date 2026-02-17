#!/usr/bin/env python
# coding=utf-8

import os
import argparse
import logging
from dotenv import load_dotenv
from FlashOAgents import OpenAIServerModel
from FlashOAgents.report_orchestrator import ReportOrchestrator
from utils import write_txt, write_json
from visualize_dag import visualize_report_dag

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

load_dotenv(override=True)


def main(args):
    custom_role_conversions = {"tool-call": "assistant", "tool-response": "user"}
    model = OpenAIServerModel(
        os.environ.get("DEFAULT_MODEL"),
        custom_role_conversions=custom_role_conversions,
        max_completion_tokens=32768,
        api_key=os.environ.get("OPENAI_API_KEY"),
        api_base=os.environ.get("OPENAI_API_BASE"),
    )

    orchestrator = ReportOrchestrator(
        model=model,
        max_section_steps=args.max_section_steps,
        summary_interval=args.summary_interval,
        section_concurrency=args.section_concurrency,
        max_section_retries=args.max_section_retries,
        prompts_type=args.prompts_type,
    )

    result = orchestrator.generate_report(args.topic)

    # Ensure output directory exists
    output_dir = os.path.dirname(args.output_report)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Save report markdown
    write_txt(args.output_report, result["report"])
    logger.info(f"Report saved to: {args.output_report}")

    # Save metadata JSON
    meta_path = os.path.splitext(args.output_report)[0] + "_meta.json"
    write_json(meta_path, {"outline": result["outline"], "metadata": result["metadata"]})
    logger.info(f"Metadata saved to: {meta_path}")

    # Generate DAG visualization
    dag_html_path = os.path.splitext(args.output_report)[0] + "_dag.html"
    visualize_report_dag(meta_path, dag_html_path)
    logger.info(f"DAG visualization saved to: {dag_html_path}")

    # Print summary
    meta = result["metadata"]
    print(f"\n{'='*60}")
    print(f"Report Generation Complete")
    print(f"{'='*60}")
    print(f"Topic:      {meta['topic']}")
    print(f"Sections:   {meta['total_sections']} total, {meta['completed_sections']} completed, {meta['failed_sections']} failed")
    print(f"Time:       {meta['elapsed_seconds']}s")
    print(f"Report:     {args.output_report}")
    print(f"Metadata:   {meta_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a Deep Research Report")

    parser.add_argument("--topic", type=str, default=None, help="Research topic (provide this or --topic_file)")
    parser.add_argument("--topic_file", type=str, default=None, help="Path to a text file containing the research topic")
    parser.add_argument("--output_report", type=str, default="./output/report.md", help="Output report path (default: ./output/report.md)")
    parser.add_argument("--max_section_steps", type=int, default=20, help="Max steps per section in Layer 2 (default: 20)")
    parser.add_argument("--summary_interval", type=int, default=8, help="Layer 2 summary interval (default: 8)")
    parser.add_argument("--section_concurrency", type=int, default=10, help="Max parallel sections (default: 5)")
    parser.add_argument("--max_section_retries", type=int, default=2, help="Max retries per section (default: 2)")
    parser.add_argument("--prompts_type", type=str, default="default", help="Layer 2 prompt type (default: default)")

    args = parser.parse_args()

    # Resolve topic: --topic_file takes precedence if both provided
    if args.topic_file:
        with open(args.topic_file, "r", encoding="utf-8") as f:
            args.topic = f.read().strip()
    if not args.topic:
        parser.error("Must provide --topic or --topic_file")

    main(args)
