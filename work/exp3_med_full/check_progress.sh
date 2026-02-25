#!/bin/bash
# 实时检查ResearchQA推理进度

OUTPUT_FILE="work/exp3_med_full/assets/output/report_researchqa_med_test10_med.jsonl"

echo "========== ResearchQA推理进度监控 =========="
echo "启动时间: 22:23"
echo "当前时间: $(date '+%H:%M:%S')"
echo

# 检查进程
PID=$(ps aux | grep "step2_run_eval.py.*researchqa_med_test10" | grep -v grep | awk '{print $2}')
if [ -n "$PID" ]; then
    echo "✅ 推理进程运行中 (PID: $PID)"
    # 查看CPU时间
    ps -p $PID -o pid,etime,time,cmd | tail -1
else
    echo "❌ 推理进程未找到"
fi

echo
echo "========== 输出文件状态 =========="
if [ -f "$OUTPUT_FILE" ]; then
    COMPLETED=$(wc -l < "$OUTPUT_FILE")
    echo "✅ 已完成: $COMPLETED / 10"
    
    # 显示最后一条的任务ID
    LAST_TASK=$(tail -1 "$OUTPUT_FILE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('task_id', 'N/A'))" 2>/dev/null || echo "解析失败")
    echo "   最后完成的task_id: $LAST_TASK"
else
    echo "⏳ 输出文件尚未生成（首条问题处理中...）"
fi

echo
echo "========== 预计完成时间 =========="
echo "每条预计: 25-30分钟"
echo "3并发 × 10条 ≈ 80-100分钟总时长"
echo "预计完成: 23:45 - 00:00"
