#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from count_module import CountPredictor


def yolo_to_count_detections(yolo_result):
    detections = []
    boxes = yolo_result.boxes
    if boxes is None or len(boxes) == 0:
        return detections
    xyxys = boxes.xyxy.cpu().tolist()
    class_ids = [int(value) for value in boxes.cls.cpu().tolist()]
    confs = [float(value) for value in boxes.conf.cpu().tolist()]
    for xyxy, class_id, conf in zip(xyxys, class_ids, confs):
        detections.append(
            {
                "xyxy": [float(value) for value in xyxy],
                "class_id": class_id,
                "conf": conf,
            }
        )
    return detections


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run YOLO detection, then append product counts.")
    parser.add_argument("--image", required=True)
    parser.add_argument(
        "--yolo-weights",
        default="runtime/runs/yolov8l_img960_ep120_perf_screen_20260517/weights/best.pt",
    )
    parser.add_argument("--count-weights", default="weights/count_best.pt")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--conf", type=float, default=0.25)
    return parser.parse_args()


def main() -> None:
    from ultralytics import YOLO

    args = parse_args()
    yolo = YOLO(args.yolo_weights)
    yolo_result = yolo.predict(
        source=args.image,
        imgsz=args.imgsz,
        conf=args.conf,
        device=args.device,
        verbose=False,
    )[0]
    detections = yolo_to_count_detections(yolo_result)

    counter = CountPredictor(args.count_weights, device=args.device)
    counted = counter.predict(args.image, detections)
    print(json.dumps(counted, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
