#!/usr/bin/env python3
"""监控DRB2和DRB实验进度"""
import json
import os
from datetime import datetime

def count_completed(jsonl_path):
    """统计已完成的任务数"""
    if not os.path.exists(jsonl_path):
        return 0
    count = 0
    with open(jsonl_path, 'r') as f:
        for line in f:
            if line.strip():
                count += 1
    return count

def get_avg_report_length(jsonl_path):
    """统计平均报告长度"""
    if not os.path.exists(jsonl_path):
        return 0
    lengths = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                result = data.get('agent_result', '')
                lengths.append(len(result))
    return sum(lengths) / len(lengths) if lengths else 0

def tail_log(log_path, n=10):
    """读取日志最后n行"""
    if not os.path.exists(log_path):
        return "日志文件不存在"
    with open(log_path, 'r') as f:
        lines = f.readlines()
    return ''.join(lines[-n:])

def main():
    exp_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 80)
    print(f"实验监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # DRB2进度
    drb2_output = os.path.join(exp_dir, "assets/output/report_drb2_med_med.jsonl")
    drb2_completed = count_completed(drb2_output)
    drb2_avg_len = get_avg_report_length(drb2_output)
    print(f"\n【DRB2实验】")
    print(f"  进度: {drb2_completed}/12 ({drb2_completed/12*100:.1f}%)")
    print(f"  平均报告长度: {drb2_avg_len:,.0f} 字符")
    print(f"  日志最后10行:")
    drb2_log = os.path.join(exp_dir, "assets/logs/run_report_drb2_med.log")
    print(tail_log(drb2_log, 10))

    # DRB进度
    drb_output = os.path.join(exp_dir, "assets/output/report_drb_med_med.jsonl")
    drb_completed = count_completed(drb_output)
    drb_avg_len = get_avg_report_length(drb_output)
    print(f"\n【DRB实验】")
    print(f"  进度: {drb_completed}/50 ({drb_completed/50*100:.1f}%)")
    print(f"  平均报告长度: {drb_avg_len:,.0f} 字符")
    print(f"  日志最后10行:")
    drb_log = os.path.join(exp_dir, "assets/logs/run_report_drb_med.log")
    print(tail_log(drb_log, 10))

    print("\n" + "=" * 80)
    print("提示：每30分钟自动检查一次，或手动运行 python3 monitor_experiments.py")
    print("=" * 80)

if __name__ == "__main__":
    main()
