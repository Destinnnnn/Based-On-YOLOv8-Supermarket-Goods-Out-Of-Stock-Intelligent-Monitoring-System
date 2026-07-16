#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.train_count_mbv3 import CountSample, read_count_csv


def iou_xyxy(a: Sequence[float], b: Sequence[float]) -> float:
    ax1, ay1, ax2, ay2 = [float(v) for v in a]
    bx1, by1, bx2, by2 = [float(v) for v in b]
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def group_gt(samples: Sequence[CountSample]) -> Dict[str, List[CountSample]]:
    grouped: Dict[str, List[CountSample]] = {}
    for sample in samples:
        grouped.setdefault(Path(sample.image).name, []).append(sample)
    return grouped


def generate_for_split(args: argparse.Namespace, split: str) -> Dict[str, float]:
    from ultralytics import YOLO

    data_root = Path(args.data_root)
    images_dir = data_root / split / "images"
    gt_csv = data_root / split / "counts.csv"
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_csv = output_dir / f"{split}_counts.csv"

    gt_samples = read_count_csv(gt_csv, images_dir)
    gt_by_image = group_gt(gt_samples)
    model = YOLO(args.yolo_weights)

    fieldnames = [
        "image",
        "class_id",
        "class_name",
        "count",
        "x1",
        "y1",
        "x2",
        "y2",
        "det_conf",
        "match_iou",
        "gt_x1",
        "gt_y1",
        "gt_x2",
        "gt_y2",
    ]
    written = 0
    images_seen = 0
    detections_seen = 0

    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        results = model.predict(
            source=str(images_dir),
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.nms_iou,
            device=args.device,
            stream=True,
            verbose=False,
        )
        for result in results:
            images_seen += 1
            image_name = Path(result.path).name
            gts = gt_by_image.get(image_name, [])
            matched_gt = set()
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue
            xyxys = boxes.xyxy.cpu().tolist()
            class_ids = [int(v) for v in boxes.cls.cpu().tolist()]
            confs = [float(v) for v in boxes.conf.cpu().tolist()]
            pred_items = sorted(zip(xyxys, class_ids, confs), key=lambda item: item[2], reverse=True)
            detections_seen += len(pred_items)

            for pred_xyxy, class_id, det_conf in pred_items:
                best_index = -1
                best_iou = 0.0
                for gt_index, gt in enumerate(gts):
                    if gt_index in matched_gt or gt.class_id != class_id:
                        continue
                    score = iou_xyxy(pred_xyxy, gt.xyxy)
                    if score > best_iou:
                        best_iou = score
                        best_index = gt_index
                if best_index < 0 or best_iou < args.iou_threshold:
                    continue
                matched_gt.add(best_index)
                gt = gts[best_index]
                writer.writerow(
                    {
                        "image": image_name,
                        "class_id": class_id,
                        "class_name": gt.class_name,
                        "count": gt.count,
                        "x1": round(float(pred_xyxy[0]), 3),
                        "y1": round(float(pred_xyxy[1]), 3),
                        "x2": round(float(pred_xyxy[2]), 3),
                        "y2": round(float(pred_xyxy[3]), 3),
                        "det_conf": round(det_conf, 6),
                        "match_iou": round(best_iou, 6),
                        "gt_x1": gt.xyxy[0],
                        "gt_y1": gt.xyxy[1],
                        "gt_x2": gt.xyxy[2],
                        "gt_y2": gt.xyxy[3],
                    }
                )
                written += 1

    stats = {
        "split": split,
        "images_seen": images_seen,
        "gt_rows": len(gt_samples),
        "detections_seen": detections_seen,
        "matched_rows": written,
        "match_rate_vs_gt": written / max(len(gt_samples), 1),
        "output_csv": str(output_csv),
    }
    (output_dir / f"{split}_stats.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(stats, ensure_ascii=False), flush=True)
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate count fine-tuning CSVs from YOLO predicted boxes.")
    parser.add_argument("--data-root", default="datasets")
    parser.add_argument("--splits", default="train,val")
    parser.add_argument(
        "--yolo-weights",
        default="runtime/runs/yolov8l_img960_ep120_perf_screen_20260517/weights/best.pt",
    )
    parser.add_argument("--output-dir", default="runtime/count_yoloft")
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--nms-iou", type=float, default=0.7)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--device", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    cli_args = parse_args()
    all_stats = [generate_for_split(cli_args, split.strip()) for split in cli_args.splits.split(",") if split.strip()]
    output_dir = Path(cli_args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "stats.json").write_text(
        json.dumps(all_stats, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
