#!/bin/bash
# 监控DRB官方评估进度

while true; do
    echo "========================================"
    date
    echo "========================================"

    # 检查进程
    if ps aux | grep "[s]tep6_rescore" > /dev/null; then
        echo "✅ 评估进程运行中"

        # 统计已完成数量
        if [ -f "assets/output/scored/report_drb_med_official_scored.jsonl" ]; then
            completed=$(wc -l < assets/output/scored/report_drb_med_official_scored.jsonl)
            echo "📊 进度: $completed/50 ($(echo "scale=1; $completed*100/50" | bc)%)"
        fi

        # 显示最后10行日志
        echo ""
        echo "最新日志:"
        tail -10 assets/logs/rescore_drb_official.log
    else
        echo "⚠️  评估进程已结束"

        # 显示最终结果
        if [ -f "assets/output/scored/report_drb_med_official_summary.json" ]; then
            echo ""
            echo "✅ 评估完成！汇总结果:"
            cat assets/output/scored/report_drb_med_official_summary.json | python3 -m json.tool
        fi

        break
    fi

    echo ""
    sleep 60  # 每分钟检查一次
done
