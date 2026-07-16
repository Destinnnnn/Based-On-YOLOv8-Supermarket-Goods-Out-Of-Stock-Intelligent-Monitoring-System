#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from count_module.model import model_from_checkpoint
from scripts.train_count_mbv3 import (
    CountCollator,
    CountCsvDataset,
    ImageGroupedBatchSampler,
    count_bucket,
    evaluate,
    select_device,
)


@torch.inference_mode()
def write_predictions_csv(
    model: torch.nn.Module,
    loader: DataLoader,
    device: torch.device,
    min_count: int,
    max_count: int,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model.eval()
    fieldnames = [
        "image",
        "class_id",
        "xyxy",
        "count_true",
        "count_pred",
        "raw_pred",
        "bucket",
        "error",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for batch in loader:
            images = batch["image"].to(device, non_blocking=True)
            class_ids = batch["class_id"].to(device, non_blocking=True)
            preds = model(images, class_ids)
            rounded = preds.round().clamp(min_count, max_count).to(torch.int64)
            for record, raw_pred, count_pred in zip(
                batch["records"],
                preds.detach().cpu().tolist(),
                rounded.cpu().tolist(),
            ):
                true_count = int(record["count_true"])
                writer.writerow(
                    {
                        "image": record["image"],
                        "class_id": int(record["class_id"]),
                        "xyxy": json.dumps([float(value) for value in record["xyxy"]], ensure_ascii=False),
                        "count_true": true_count,
                        "count_pred": int(count_pred),
                        "raw_pred": f"{float(raw_pred):.6f}",
                        "bucket": count_bucket(true_count),
                        "error": int(count_pred) - true_count,
                    }
                )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a trained count checkpoint on a counts.csv file.")
    parser.add_argument("--weights", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--image-size", type=int, default=None)
    parser.add_argument("--pad-ratio", type=float, default=None)
    parser.add_argument("--min-count", type=int, default=None)
    parser.add_argument("--max-count", type=int, default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--predictions-csv", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    checkpoint = torch.load(args.weights, map_location="cpu")
    image_size = int(args.image_size if args.image_size is not None else checkpoint.get("image_size", 224))
    pad_ratio = float(args.pad_ratio if args.pad_ratio is not None else checkpoint.get("pad_ratio", 0.08))
    min_count = int(args.min_count if args.min_count is not None else checkpoint.get("min_count", 1))
    max_count = int(args.max_count if args.max_count is not None else checkpoint.get("max_count", 56))

    dataset = CountCsvDataset(
        Path(args.csv),
        Path(args.image_dir),
        image_size=image_size,
        pad_ratio=pad_ratio,
    )
    device = select_device(args.device)
    model = model_from_checkpoint(checkpoint, pretrained=False).to(device)
    loader = DataLoader(
        dataset,
        batch_sampler=ImageGroupedBatchSampler(
            dataset.samples,
            batch_size=args.batch_size,
            shuffle=False,
            weighted=False,
            seed=42,
        ),
        num_workers=args.workers,
        pin_memory=device.type == "cuda",
        persistent_workers=args.workers > 0,
        collate_fn=CountCollator(image_size, pad_ratio),
    )
    metrics = evaluate(model, loader, device, min_count=min_count, max_count=max_count)
    text = json.dumps(metrics, indent=2, ensure_ascii=False)
    print(text)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.predictions_csv:
        write_predictions_csv(
            model,
            loader,
            device,
            min_count=min_count,
            max_count=max_count,
            output_path=Path(args.predictions_csv),
        )


if __name__ == "__main__":
    main()
