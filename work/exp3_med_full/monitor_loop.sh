#!/bin/bash
# 后台监控循环：每30分钟检查一次实验进度和错误

while true; do
    echo "========================================" >> assets/logs/monitor.log
    date >> assets/logs/monitor.log
    
    # 运行监控脚本
    python3 monitor_experiments.py >> assets/logs/monitor.log 2>&1
    
    # 检查DRB2日志中的错误
    if tail -50 assets/logs/run_report_drb2_med.log 2>/dev/null | grep -i "error\|traceback\|exception\|failed" | grep -v "RuntimeWarning" > /dev/null; then
        echo "⚠️  DRB2发现错误！" >> assets/logs/monitor.log
        tail -20 assets/logs/run_report_drb2_med.log >> assets/logs/monitor.log
    fi
    
    # 检查DRB日志中的错误
    if tail -50 assets/logs/run_report_drb_med.log 2>/dev/null | grep -i "error\|traceback\|exception\|failed" | grep -v "RuntimeWarning" > /dev/null; then
        echo "⚠️  DRB发现错误！" >> assets/logs/monitor.log
        tail -20 assets/logs/run_report_drb_med.log >> assets/logs/monitor.log
    fi
    
    # 检查进程是否还在运行
    if ! ps aux | grep "[s]tep2_run_eval.py.*drb2_med" > /dev/null; then
        echo "⚠️  DRB2进程已停止" >> assets/logs/monitor.log
    fi
    
    if ! ps aux | grep "[s]tep2_run_eval.py.*drb_med" > /dev/null; then
        echo "⚠️  DRB进程已停止" >> assets/logs/monitor.log
    fi
    
    # 等待30分钟
    sleep 1800
done
