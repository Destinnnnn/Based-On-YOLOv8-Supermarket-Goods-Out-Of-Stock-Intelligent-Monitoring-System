#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1
if [[ -z "${OMP_NUM_THREADS:-}" || "${OMP_NUM_THREADS}" == "0" ]]; then
  export OMP_NUM_THREADS=4
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_DIR="runtime/logs"
mkdir -p "$LOG_DIR" runtime/runs weights

MASTER_LOG="$LOG_DIR/count_full_pipeline.log"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$MASTER_LOG"
}

run_stage() {
  local name="$1"
  shift
  local stage_log="$LOG_DIR/${name}.log"
  log "START ${name}"
  log "COMMAND $*"
  "$@" > "$stage_log" 2>&1
  log "DONE ${name}"
}

log "Count full pipeline started"
log "Working directory: $ROOT_DIR"

run_stage check_count_dataset \
  python scripts/check_count_dataset.py \
    --data-root datasets \
    --output-dir runtime/count_dataset_checks \
    --sample-crops 24

run_stage train_count_mbv3_gt_224 \
  python scripts/train_count_mbv3.py \
    --data-root datasets \
    --output runtime/runs/count_mbv3_gt_224 \
    --test-csv datasets/test/counts.csv \
    --epochs 30 \
    --batch-size 256 \
    --workers 16 \
    --log-interval 10 \
    --device cuda

run_stage generate_count_yoloft_csv \
  python scripts/generate_count_yoloft_csv.py \
    --data-root datasets \
    --yolo-weights runtime/runs/yolov8l_img960_ep120_perf_screen_20260517/weights/best.pt \
    --output-dir runtime/count_yoloft \
    --splits train,val,test \
    --device cuda

run_stage train_count_mbv3_yoloft_224 \
  python scripts/train_count_mbv3.py \
    --data-root datasets \
    --train-csv runtime/count_yoloft/train_counts.csv \
    --val-csv runtime/count_yoloft/val_counts.csv \
    --train-image-dir datasets/train/images \
    --val-image-dir datasets/val/images \
    --init-weights runtime/runs/count_mbv3_gt_224/weights/best.pt \
    --output runtime/runs/count_mbv3_yoloft_224 \
    --test-csv runtime/count_yoloft/test_counts.csv \
    --test-image-dir datasets/test/images \
    --epochs 10 \
    --batch-size 256 \
    --workers 16 \
    --log-interval 10 \
    --device cuda

mkdir -p weights
cp runtime/runs/count_mbv3_yoloft_224/weights/best.pt weights/count_best.pt
log "Copied final checkpoint to weights/count_best.pt"

run_stage eval_count_mbv3_final \
  python scripts/eval_count_mbv3.py \
    --weights weights/count_best.pt \
    --csv runtime/count_yoloft/test_counts.csv \
    --image-dir datasets/test/images \
    --device cuda \
    --output runtime/runs/count_mbv3_yoloft_224/final_test_metrics.json

log "Count full pipeline finished successfully"
