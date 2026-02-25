#!/bin/bash
# 自动检测推理完成并触发评分

OUTPUT_FILE="work/exp3_med_full/assets/output/report_researchqa_med_test10_med.jsonl"
SCORE_CMD="python3 work/exp3_med_full/step4_score_researchqa.py \
    --input work/exp3_med_full/assets/output/report_researchqa_med_test10_med.jsonl \
    --output work/exp3_med_full/assets/output/scored/report_researchqa_med_test10_scored.jsonl \
    --framework report \
    --bench researchqa_med_test10"

echo "等待推理完成（目标：10条）..."
while true; do
    if [ -f "$OUTPUT_FILE" ]; then
        COMPLETED=$(wc -l < "$OUTPUT_FILE")
        echo "[$(date '+%H:%M:%S')] 已完成: $COMPLETED / 10"
        
        if [ "$COMPLETED" -ge 10 ]; then
            echo "✅ 推理完成！开始评分..."
            mkdir -p work/exp3_med_full/assets/output/scored
            eval "$SCORE_CMD" 2>&1 | tee work/exp3_med_full/assets/logs/score_researchqa_test10.log
            echo "✅ 评分完成！"
            break
        fi
    else
        echo "[$(date '+%H:%M:%S')] 等待输出文件生成..."
    fi
    
    sleep 120  # 每2分钟检查一次
done
