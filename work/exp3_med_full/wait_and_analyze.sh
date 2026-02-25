#!/bin/bash
# 等待推理完成并进行初步分析

OUTPUT_FILE="work/exp3_med_full/assets/output/report_researchqa_med_test10_med.jsonl"
TARGET=10

echo "⏰ 等待ResearchQA推理完成..."
echo "目标: $TARGET 条"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo

while true; do
    if [ -f "$OUTPUT_FILE" ]; then
        COMPLETED=$(wc -l < "$OUTPUT_FILE")
        TIMESTAMP=$(date '+%H:%M:%S')
        echo "[$TIMESTAMP] ✅ 已完成: $COMPLETED / $TARGET"
        
        if [ "$COMPLETED" -ge "$TARGET" ]; then
            echo
            echo "🎉 推理全部完成！"
            echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
            echo
            
            # 快速预览
            echo "========== 快速预览 =========="
            echo "前3条的task_id:"
            head -3 "$OUTPUT_FILE" | python3 -c "
import json, sys
for i, line in enumerate(sys.stdin, 1):
    data = json.loads(line)
    print(f'{i}. {data.get(\"task_id\", \"N/A\")} - {len(data.get(\"report\", \"\"))} chars')
" 2>/dev/null || echo "解析失败"
            
            echo
            echo "========== 启动评分 =========="
            bash work/exp3_med_full/auto_score_when_ready.sh
            break
        fi
    else
        TIMESTAMP=$(date '+%H:%M:%S')
        echo "[$TIMESTAMP] ⏳ 等待首条完成..."
    fi
    
    sleep 180  # 每3分钟检查一次
done
