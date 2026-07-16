#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from count_module.transforms import crop_box
from scripts.train_count_mbv3 import CountSample, read_count_csv


def count_label_rows(labels_dir: Path) -> int:
    total = 0
    for path in labels_dir.glob("*.txt"):
        with path.open("r", encoding="utf-8") as handle:
            total += sum(1 for line in handle if line.strip())
    return total


def save_sample_crops(samples: List[CountSample], output_dir: Path, split: str, sample_count: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, sample in enumerate(samples[:sample_count]):
        with Image.open(sample.image_path) as image:
            image = image.convert("RGB")
            crop = crop_box(image, sample.xyxy, pad_ratio=0.08)
        draw = ImageDraw.Draw(crop)
        text = f"cls={sample.class_id} count={sample.count}"
        draw.rectangle((0, 0, min(crop.width, 260), 24), fill=(0, 0, 0))
        draw.text((4, 4), text, fill=(255, 255, 255))
        safe_name = Path(sample.image).stem
        crop.save(output_dir / f"{split}_{index:04d}_{safe_name}_cls{sample.class_id}_count{sample.count}.jpg")


def inspect_split(data_root: Path, split: str, output_dir: Path, sample_count: int, rng: random.Random) -> Dict[str, object]:
    csv_path = data_root / split / "counts.csv"
    image_dir = data_root / split / "images"
    labels_dir = data_root / split / "labels"
    samples = read_count_csv(csv_path, image_dir)
    label_rows = count_label_rows(labels_dir)
    counts = Counter(sample.count for sample in samples)
    class_rows = Counter(sample.class_id for sample in samples)

    sampled = samples[:]
    rng.shuffle(sampled)
    if sample_count > 0:
        save_sample_crops(sampled, output_dir / "crops", split, sample_count)

    stats = {
        "split": split,
        "counts_csv_rows": len(samples),
        "yolo_label_rows": label_rows,
        "rows_match": len(samples) == label_rows,
        "min_count": min(counts) if counts else None,
        "max_count": max(counts) if counts else None,
        "count_distribution_top20": counts.most_common(20),
        "num_classes_present": len(class_rows),
        "class_distribution_top20": class_rows.most_common(20),
    }
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate count CSVs and save sample crop previews.")
    parser.add_argument("--data-root", default="datasets")
    parser.add_argument("--splits", default="train,val,test")
    parser.add_argument("--output-dir", default="runtime/count_dataset_checks")
    parser.add_argument("--sample-crops", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    root = Path(args.data_root)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    results = [inspect_split(root, split.strip(), out, args.sample_crops, rng) for split in args.splits.split(",") if split.strip()]
    (out / "summary.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    for item in results:
        print(json.dumps(item, ensure_ascii=False), flush=True)
