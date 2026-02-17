#!/bin/bash

python run_deep_report.py \
    --topic "大语言模型对科学研究的影响" \
    --output_report ./output/llm_science_report2.md \
    --max_section_steps 20 \
    --summary_interval 8 \
    --section_concurrency 10
