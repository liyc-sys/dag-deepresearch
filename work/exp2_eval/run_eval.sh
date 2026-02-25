#!/bin/bash
# 运行dag-deepresearch评测脚本
# 先seed18，再seed16；依次测三个数据集

EXP_DIR="$(dirname "$0")"
LOG_DIR="$EXP_DIR/assets/logs"
DAG_ROOT="$(dirname "$EXP_DIR")/.."

mkdir -p "$LOG_DIR"

cd "$DAG_ROOT"
echo "工作目录: $(pwd)"

echo "[$(date)] 开始评测 seed18 × 全部数据集" | tee -a "$LOG_DIR/eval_main.log"

python3 "$EXP_DIR/step2_run_eval.py" \
    --models seed18 \
    --datasets bc_en bc_zh dsq \
    --concurrency 5 \
    --max_steps 40 \
    --summary_interval 8 \
    2>&1 | tee -a "$LOG_DIR/eval_seed18.log"

echo "[$(date)] seed18完成，开始评测 seed16" | tee -a "$LOG_DIR/eval_main.log"

python3 "$EXP_DIR/step2_run_eval.py" \
    --models seed16 \
    --datasets bc_en bc_zh dsq \
    --concurrency 5 \
    --max_steps 40 \
    --summary_interval 8 \
    2>&1 | tee -a "$LOG_DIR/eval_seed16.log"

echo "[$(date)] 所有评测完成" | tee -a "$LOG_DIR/eval_main.log"
