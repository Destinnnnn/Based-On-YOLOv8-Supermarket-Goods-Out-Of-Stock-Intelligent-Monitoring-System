#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset, Sampler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from count_module.model import build_count_model, model_from_checkpoint
from count_module.transforms import crop_to_tensor


COUNT_BUCKETS: Tuple[Tuple[str, int, Optional[int]], ...] = (
    ("1", 1, 1),
    ("2-3", 2, 3),
    ("4-6", 4, 6),
    ("7-9", 7, 9),
    ("10-19", 10, 19),
    ("20+", 20, None),
)
DEFAULT_BUCKET_LOSS_WEIGHTS = "1:1,2-3:1.5,4-6:2,7-9:3,10-19:5,20+:8"


@dataclass(frozen=True)
class CountSample:
    image: str
    image_path: str
    class_id: int
    class_name: str
    count: int
    xyxy: Tuple[float, float, float, float]


def normalize_bucket_name(name: str) -> str:
    cleaned = name.strip()
    aliases = {
        "count=1": "1",
        "count1": "1",
        "ge20": "20+",
        "20plus": "20+",
    }
    return aliases.get(cleaned.lower(), cleaned)


def count_bucket(count: float) -> str:
    value = int(round(float(count)))
    for name, low, high in COUNT_BUCKETS:
        if high is None:
            if value >= low:
                return name
        elif low <= value <= high:
            return name
    return "other"


def parse_bucket_loss_weights(spec: str) -> Dict[str, float]:
    weights = {name: 1.0 for name, _, _ in COUNT_BUCKETS}
    if not spec:
        return weights

    valid_names = set(weights)
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise ValueError(f"Invalid bucket weight '{chunk}', expected BUCKET:WEIGHT")
        raw_name, raw_weight = chunk.split(":", 1)
        name = normalize_bucket_name(raw_name)
        if name not in valid_names:
            raise ValueError(f"Unknown count bucket '{raw_name}'. Valid buckets: {sorted(valid_names)}")
        weight = float(raw_weight)
        if not math.isfinite(weight) or weight < 0:
            raise ValueError(f"Bucket weight for '{name}' must be a finite non-negative number")
        weights[name] = weight
    return weights


def bucket_weight_tensor(targets: torch.Tensor, bucket_weights: Dict[str, float]) -> torch.Tensor:
    weights = torch.ones_like(targets, dtype=torch.float32)
    for name, low, high in COUNT_BUCKETS:
        if high is None:
            mask = targets >= low
        else:
            mask = (targets >= low) & (targets <= high)
        weights = torch.where(mask, torch.full_like(weights, float(bucket_weights.get(name, 1.0))), weights)
    return weights


def new_eval_stats() -> Dict[str, float]:
    return {
        "n": 0.0,
        "abs": 0.0,
        "exact": 0.0,
        "pm1": 0.0,
        "pm2": 0.0,
        "pm3": 0.0,
        "pred_sum": 0.0,
        "true_sum": 0.0,
    }


def update_eval_stats(
    stats: Dict[str, float],
    rounded_diff: torch.Tensor,
    rounded_preds: torch.Tensor,
    targets: torch.Tensor,
) -> None:
    n = int(targets.numel())
    if n == 0:
        return
    stats["n"] += float(n)
    stats["abs"] += rounded_diff.sum().item()
    stats["exact"] += (rounded_diff == 0).sum().item()
    stats["pm1"] += (rounded_diff <= 1).sum().item()
    stats["pm2"] += (rounded_diff <= 2).sum().item()
    stats["pm3"] += (rounded_diff <= 3).sum().item()
    stats["pred_sum"] += rounded_preds.sum().item()
    stats["true_sum"] += targets.sum().item()


def finalize_eval_stats(stats: Dict[str, float]) -> Dict[str, float]:
    n = int(stats["n"])
    denom = max(n, 1)
    return {
        "n": float(n),
        "mae": stats["abs"] / denom,
        "exact_acc": stats["exact"] / denom,
        "pm1_acc": stats["pm1"] / denom,
        "pm2_acc": stats["pm2"] / denom,
        "pm3_acc": stats["pm3"] / denom,
        "bias": (stats["pred_sum"] - stats["true_sum"]) / denom,
    }


class CountCsvDataset(Dataset):
    def __init__(
        self,
        csv_path: Path,
        image_dir: Optional[Path] = None,
        image_size: int = 224,
        pad_ratio: float = 0.08,
        limit: Optional[int] = None,
    ) -> None:
        self.csv_path = Path(csv_path)
        self.image_dir = Path(image_dir) if image_dir else self.csv_path.parent / "images"
        self.image_size = image_size
        self.pad_ratio = pad_ratio
        self.samples = read_count_csv(self.csv_path, self.image_dir)
        if limit is not None:
            self.samples = self.samples[:limit]
        if not self.samples:
            raise ValueError(f"No samples found in {self.csv_path}")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> CountSample:
        return self.samples[index]


def read_count_csv(csv_path: Path, image_dir: Optional[Path] = None) -> List[CountSample]:
    csv_path = Path(csv_path)
    base_dir = Path(image_dir) if image_dir else csv_path.parent / "images"
    samples: List[CountSample] = []
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"image", "class_id", "count", "x1", "y1", "x2", "y2"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{csv_path} is missing columns: {sorted(missing)}")
        for row in reader:
            image_value = row["image"]
            image_path = Path(image_value)
            if not image_path.is_absolute():
                image_path = base_dir / image_value
            samples.append(
                CountSample(
                    image=image_value,
                    image_path=str(image_path),
                    class_id=int(float(row["class_id"])),
                    class_name=row.get("class_name", ""),
                    count=int(round(float(row["count"]))),
                    xyxy=(
                        float(row["x1"]),
                        float(row["y1"]),
                        float(row["x2"]),
                        float(row["y2"]),
                    ),
                )
            )
    return samples


def infer_num_classes(data_root: Path, fallback: int = 93) -> int:
    data_yaml = data_root / "data.yaml"
    classes_txt = data_root / "classes.txt"
    if data_yaml.exists():
        try:
            import yaml

            data = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
            if "nc" in data:
                return int(data["nc"])
        except Exception:
            pass
    if classes_txt.exists():
        return len([line for line in classes_txt.read_text(encoding="utf-8").splitlines() if line.strip()])
    return fallback


class ImageGroupedBatchSampler(Sampler[List[int]]):
    """Yield batches grouped by image so each worker decodes an image once."""

    def __init__(
        self,
        samples: Sequence[CountSample],
        batch_size: int,
        shuffle: bool,
        weighted: bool,
        seed: int,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.samples = samples
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.weighted = weighted
        self.seed = seed
        self.epoch = 0

        groups_by_path: Dict[str, List[int]] = {}
        for index, sample in enumerate(samples):
            groups_by_path.setdefault(sample.image_path, []).append(index)
        self.groups = list(groups_by_path.values())

        count_freq = Counter(sample.count for sample in samples)
        sample_weights = [1.0 / math.sqrt(count_freq[sample.count]) for sample in samples]
        self.group_weights = [max(sample_weights[index] for index in group) for group in self.groups]

    def __iter__(self) -> Iterator[List[int]]:
        group_count = len(self.groups)
        order = list(range(group_count))
        epoch_seed = self.seed + self.epoch
        self.epoch += 1

        if self.weighted:
            generator = torch.Generator().manual_seed(epoch_seed)
            weights = torch.tensor(self.group_weights, dtype=torch.double)
            order = torch.multinomial(weights, group_count, replacement=True, generator=generator).tolist()
        elif self.shuffle:
            rng = random.Random(epoch_seed)
            rng.shuffle(order)

        batch: List[int] = []
        for group_index in order:
            group = self.groups[group_index]
            if batch and len(batch) + len(group) > self.batch_size:
                yield batch
                batch = []
            if len(group) > self.batch_size:
                if batch:
                    yield batch
                    batch = []
                yield list(group)
            else:
                batch.extend(group)
        if batch:
            yield batch

    def __len__(self) -> int:
        return max(1, math.ceil(len(self.samples) / self.batch_size))


class CountCollator:
    def __init__(self, image_size: int = 224, pad_ratio: float = 0.08) -> None:
        self.image_size = image_size
        self.pad_ratio = pad_ratio

    def __call__(self, batch: Sequence[CountSample]) -> Dict[str, Any]:
        images: List[torch.Tensor] = []
        class_ids: List[int] = []
        counts: List[float] = []
        records: List[Dict[str, Any]] = []
        samples_by_path: Dict[str, List[CountSample]] = {}
        for sample in batch:
            samples_by_path.setdefault(sample.image_path, []).append(sample)

        for image_path, samples in samples_by_path.items():
            with Image.open(image_path) as image:
                image = image.convert("RGB")
                for sample in samples:
                    images.append(
                        crop_to_tensor(
                            image,
                            sample.xyxy,
                            image_size=self.image_size,
                            pad_ratio=self.pad_ratio,
                        )
                    )
                    class_ids.append(sample.class_id)
                    counts.append(float(sample.count))
                    records.append(
                        {
                            "image": sample.image,
                            "image_path": sample.image_path,
                            "class_id": sample.class_id,
                            "class_name": sample.class_name,
                            "xyxy": sample.xyxy,
                            "count_true": sample.count,
                        }
                    )

        return {
            "image": torch.stack(images),
            "class_id": torch.tensor(class_ids, dtype=torch.long),
            "count": torch.tensor(counts, dtype=torch.float32),
            "records": records,
        }


def collate_batch(batch: Sequence[CountSample]) -> Dict[str, Any]:
    return CountCollator()(batch)


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def select_device(device_arg: str) -> torch.device:
    if device_arg == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(device_arg)


def build_or_load_model(args: argparse.Namespace, device: torch.device) -> nn.Module:
    if args.init_weights:
        checkpoint = torch.load(args.init_weights, map_location="cpu")
        model = model_from_checkpoint(checkpoint, pretrained=False)
    else:
        try:
            model = build_count_model(
                num_classes=args.num_classes,
                embedding_dim=args.embedding_dim,
                hidden_dim=args.hidden_dim,
                dropout=args.dropout,
                pretrained=args.pretrained,
            )
        except Exception as exc:
            if not args.pretrained:
                raise
            print(f"Pretrained MobileNetV3 weights unavailable ({exc}); falling back to random init.")
            model = build_count_model(
                num_classes=args.num_classes,
                embedding_dim=args.embedding_dim,
                hidden_dim=args.hidden_dim,
                dropout=args.dropout,
                pretrained=False,
            )
    return model.to(device)


@torch.inference_mode()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    min_count: int = 1,
    max_count: int = 56,
) -> Dict[str, Any]:
    model.eval()
    total = 0
    raw_abs = 0.0
    rounded_abs = 0.0
    exact = 0
    pm1 = 0
    pm2 = 0
    pm3 = 0
    overall_stats = new_eval_stats()
    bucket_stats = {name: new_eval_stats() for name, _, _ in COUNT_BUCKETS}

    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        class_ids = batch["class_id"].to(device, non_blocking=True)
        targets = batch["count"].to(device, non_blocking=True)
        preds = model(images, class_ids)
        rounded = preds.round().clamp(min_count, max_count)
        raw_diff = (preds - targets).abs()
        rounded_diff = (rounded - targets).abs()

        batch_size = targets.numel()
        total += batch_size
        raw_abs += raw_diff.sum().item()
        rounded_abs += rounded_diff.sum().item()
        exact += (rounded_diff == 0).sum().item()
        pm1 += (rounded_diff <= 1).sum().item()
        pm2 += (rounded_diff <= 2).sum().item()
        pm3 += (rounded_diff <= 3).sum().item()
        update_eval_stats(overall_stats, rounded_diff, rounded, targets)

        for name, low, high in COUNT_BUCKETS:
            if high is None:
                mask = targets >= low
            else:
                mask = (targets >= low) & (targets <= high)
            n = int(mask.sum().item())
            if n == 0:
                continue
            update_eval_stats(bucket_stats[name], rounded_diff[mask], rounded[mask], targets[mask])

    metrics: Dict[str, Any] = {
        "n": float(total),
        "mae_raw": raw_abs / max(total, 1),
        "mae_rounded": rounded_abs / max(total, 1),
        "exact_acc": exact / max(total, 1),
        "pm1_acc": pm1 / max(total, 1),
        "pm2_acc": pm2 / max(total, 1),
        "pm3_acc": pm3 / max(total, 1),
        "bias": finalize_eval_stats(overall_stats)["bias"],
        "buckets": {},
    }
    for name, stats in bucket_stats.items():
        bucket_metrics = finalize_eval_stats(stats)
        metrics["buckets"][name] = bucket_metrics

        legacy_name = "count1" if name == "1" else None
        if legacy_name:
            metrics[f"{legacy_name}_n"] = bucket_metrics["n"]
            metrics[f"{legacy_name}_mae_rounded"] = bucket_metrics["mae"]
            metrics[f"{legacy_name}_exact_acc"] = bucket_metrics["exact_acc"]
            metrics[f"{legacy_name}_pm1_acc"] = bucket_metrics["pm1_acc"]

    ge10_stats = new_eval_stats()
    for name in ("10-19", "20+"):
        stats = bucket_stats[name]
        for key in ge10_stats:
            ge10_stats[key] += stats[key]
    ge10_metrics = finalize_eval_stats(ge10_stats)
    metrics["ge10_n"] = ge10_metrics["n"]
    metrics["ge10_mae_rounded"] = ge10_metrics["mae"]
    metrics["ge10_exact_acc"] = ge10_metrics["exact_acc"]
    metrics["ge10_pm1_acc"] = ge10_metrics["pm1_acc"]
    return metrics


def save_checkpoint(
    path: Path,
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    epoch: int,
    metrics: Dict[str, Any],
    args: argparse.Namespace,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    base_model = model.module if hasattr(model, "module") else model
    checkpoint = {
        "epoch": epoch,
        "model": base_model.state_dict(),
        "model_config": base_model.config(),
        "optimizer": optimizer.state_dict(),
        "metrics": metrics,
        "image_size": args.image_size,
        "pad_ratio": args.pad_ratio,
        "min_count": args.min_count,
        "max_count": args.max_count,
        "loss_weight_mode": args.loss_weight_mode,
        "bucket_loss_weights": getattr(args, "resolved_bucket_loss_weights", None),
    }
    torch.save(checkpoint, path)


def train(args: argparse.Namespace) -> None:
    set_seed(args.seed)
    data_root = Path(args.data_root)
    if args.num_classes is None:
        args.num_classes = infer_num_classes(data_root)

    train_csv = Path(args.train_csv) if args.train_csv else data_root / "train" / "counts.csv"
    val_csv = Path(args.val_csv) if args.val_csv else data_root / "val" / "counts.csv"
    test_csv = Path(args.test_csv) if args.test_csv else None
    train_image_dir = Path(args.train_image_dir) if args.train_image_dir else data_root / "train" / "images"
    val_image_dir = Path(args.val_image_dir) if args.val_image_dir else data_root / "val" / "images"
    test_image_dir = Path(args.test_image_dir) if args.test_image_dir else data_root / "test" / "images"

    train_dataset = CountCsvDataset(
        train_csv,
        train_image_dir,
        image_size=args.image_size,
        pad_ratio=args.pad_ratio,
        limit=args.limit_train,
    )
    val_dataset = CountCsvDataset(
        val_csv,
        val_image_dir,
        image_size=args.image_size,
        pad_ratio=args.pad_ratio,
        limit=args.limit_val,
    )

    device = select_device(args.device)
    use_cuda = device.type == "cuda"
    model = build_or_load_model(args, device)
    criterion = nn.SmoothL1Loss(reduction="none")
    bucket_loss_weights = parse_bucket_loss_weights(args.bucket_loss_weights)
    args.resolved_bucket_loss_weights = bucket_loss_weights
    print(
        f"loss_weight_mode={args.loss_weight_mode} bucket_loss_weights={json.dumps(bucket_loss_weights, ensure_ascii=False)}",
        flush=True,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(args.epochs, 1))
    scaler = torch.amp.GradScaler("cuda", enabled=use_cuda and args.amp)

    train_loader = DataLoader(
        train_dataset,
        batch_sampler=ImageGroupedBatchSampler(
            train_dataset.samples,
            batch_size=args.batch_size,
            shuffle=not args.weighted_sampler,
            weighted=args.weighted_sampler,
            seed=args.seed,
        ),
        num_workers=args.workers,
        pin_memory=use_cuda,
        persistent_workers=args.workers > 0,
        collate_fn=CountCollator(args.image_size, args.pad_ratio),
    )
    val_loader = DataLoader(
        val_dataset,
        batch_sampler=ImageGroupedBatchSampler(
            val_dataset.samples,
            batch_size=args.batch_size,
            shuffle=False,
            weighted=False,
            seed=args.seed,
        ),
        num_workers=args.workers,
        pin_memory=use_cuda,
        persistent_workers=args.workers > 0,
        collate_fn=CountCollator(args.image_size, args.pad_ratio),
    )

    output_dir = Path(args.output)
    weights_dir = output_dir / "weights"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "train_args.json").write_text(
        json.dumps(vars(args), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    best_mae = float("inf")
    history: List[Dict[str, Any]] = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        seen = 0
        for step, batch in enumerate(train_loader, start=1):
            images = batch["image"].to(device, non_blocking=True)
            class_ids = batch["class_id"].to(device, non_blocking=True)
            targets = batch["count"].to(device, non_blocking=True)

            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(device_type=device.type, enabled=use_cuda and args.amp):
                preds = model(images, class_ids)
                sample_losses = criterion(preds, targets)
                if args.loss_weight_mode == "bucket":
                    loss_weights = bucket_weight_tensor(targets, bucket_loss_weights).to(device, non_blocking=True)
                    loss = (sample_losses * loss_weights).sum() / loss_weights.sum().clamp_min(1e-6)
                else:
                    loss = sample_losses.mean()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            batch_size = targets.numel()
            running_loss += loss.item() * batch_size
            seen += batch_size
            if args.log_interval > 0 and step % args.log_interval == 0:
                print(
                    "epoch={epoch} step={step}/{total} seen={seen} loss={loss:.4f}".format(
                        epoch=epoch,
                        step=step,
                        total=len(train_loader),
                        seen=seen,
                        loss=running_loss / max(seen, 1),
                    ),
                    flush=True,
                )

        scheduler.step()
        val_metrics = evaluate(model, val_loader, device, min_count=args.min_count, max_count=args.max_count)
        val_metrics["epoch"] = float(epoch)
        val_metrics["train_loss"] = running_loss / max(seen, 1)
        val_metrics["lr"] = optimizer.param_groups[0]["lr"]
        history.append(val_metrics)
        print(
            "epoch={epoch} loss={loss:.4f} val_mae={mae:.4f} exact={exact:.4f} pm1={pm1:.4f}".format(
                epoch=epoch,
                loss=val_metrics["train_loss"],
                mae=val_metrics["mae_rounded"],
                exact=val_metrics["exact_acc"],
                pm1=val_metrics["pm1_acc"],
            ),
            flush=True,
        )

        save_checkpoint(weights_dir / "last.pt", model, optimizer, epoch, val_metrics, args)
        if val_metrics["mae_rounded"] < best_mae:
            best_mae = val_metrics["mae_rounded"]
            save_checkpoint(weights_dir / "best.pt", model, optimizer, epoch, val_metrics, args)

    (output_dir / "metrics.json").write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if test_csv and test_csv.exists():
        test_dataset = CountCsvDataset(
            test_csv,
            test_image_dir,
            image_size=args.image_size,
            pad_ratio=args.pad_ratio,
            limit=args.limit_test,
        )
        test_loader = DataLoader(
            test_dataset,
            batch_sampler=ImageGroupedBatchSampler(
                test_dataset.samples,
                batch_size=args.batch_size,
                shuffle=False,
                weighted=False,
                seed=args.seed,
            ),
            num_workers=args.workers,
            pin_memory=use_cuda,
            persistent_workers=args.workers > 0,
            collate_fn=CountCollator(args.image_size, args.pad_ratio),
        )
        best_checkpoint = torch.load(weights_dir / "best.pt", map_location="cpu")
        best_model = model_from_checkpoint(best_checkpoint, pretrained=False).to(device)
        test_metrics = evaluate(best_model, test_loader, device, args.min_count, args.max_count)
        (output_dir / "test_metrics.json").write_text(
            json.dumps(test_metrics, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"test_metrics={json.dumps(test_metrics, ensure_ascii=False)}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train MobileNetV3 count regressor from counts.csv.")
    parser.add_argument("--data-root", default="datasets")
    parser.add_argument("--train-csv", default=None)
    parser.add_argument("--val-csv", default=None)
    parser.add_argument("--test-csv", default=None)
    parser.add_argument("--train-image-dir", default=None)
    parser.add_argument("--val-image-dir", default=None)
    parser.add_argument("--test-image-dir", default=None)
    parser.add_argument("--output", default="runtime/runs/count_mbv3_gt_224")
    parser.add_argument("--init-weights", default=None, help="Fine-tune from an existing count checkpoint.")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--log-interval", type=int, default=200)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--pad-ratio", type=float, default=0.08)
    parser.add_argument("--min-count", type=int, default=1)
    parser.add_argument("--max-count", type=int, default=56)
    parser.add_argument("--num-classes", type=int, default=None)
    parser.add_argument("--embedding-dim", type=int, default=32)
    parser.add_argument("--hidden-dim", type=int, default=256)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit-train", type=int, default=None)
    parser.add_argument("--limit-val", type=int, default=None)
    parser.add_argument("--limit-test", type=int, default=None)
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--pretrained", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--weighted-sampler", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--loss-weight-mode", choices=("none", "bucket"), default="none")
    parser.add_argument("--bucket-loss-weights", default=DEFAULT_BUCKET_LOSS_WEIGHTS)
    return parser.parse_args()


if __name__ == "__main__":
    train(parse_args())
