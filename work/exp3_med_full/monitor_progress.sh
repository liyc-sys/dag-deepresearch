#!/bin/bash
# 监控ResearchQA Report框架推理进度

LOG_FILE="/tmp/claude-1000/-mnt-bn-med-mllm-lfv2-linjh-project-learn-2026-q1-eval-dag-deepresearch/tasks/bf85808.output"
OUTPUT_FILE="work/exp3_med_full/assets/output/report_researchqa_med_test10_med.jsonl"

while true; do
    clear
    echo "========== ResearchQA Report Framework - Progress Monitor =========="
    echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo

    # 统计已完成的条数
    if [ -f "$OUTPUT_FILE" ]; then
        COMPLETED=$(wc -l < "$OUTPUT_FILE")
    else
        COMPLETED=0
    fi
    echo "✅ Completed: $COMPLETED / 10"
    echo
    
    # 显示最新的日志（最后30行）
    echo "========== Latest Logs (last 30 lines) =========="
    if [ -f "$LOG_FILE" ]; then
        tail -30 "$LOG_FILE" | grep -E "INFO|ERROR|Starting report|Completed section|Final report generated" || echo "No relevant logs yet..."
    else
        echo "Log file not found"
    fi
    
    # 如果完成了10条，退出监控
    if [ "$COMPLETED" -ge 10 ]; then
        echo
        echo "🎉 All 10 questions completed!"
        break
    fi
    
    # 每60秒刷新一次
    sleep 60
done
