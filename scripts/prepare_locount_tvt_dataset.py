"""Prepare the 93-class Locount dataset with strict train/val/test splits.

The split policy is intentionally different from the previous mixed 80/20
cleaned dataset:

- original Locount Train -> new train/val, image-level split
- original Locount Test -> new test
- current 93 retained classes are preserved and remapped to 0..92

Images can be moved into the project dataset to avoid a large temporary copy on
the same D: drive.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_ROOT = Path(r"D:\Dataset")
DEFAULT_TARGET_ROOT = PROJECT_ROOT / "datasets"
DEFAULT_CLASSES_FILE = PROJECT_ROOT / "config" / "locount_93_classes.txt"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


@dataclass(frozen=True)
class SourceSplit:
    name: str
    image_dir: Path
    label_dir: Path


@dataclass(frozen=True)
class Annotation:
    x1: float
    y1: float
    x2: float
    y2: float
    label: str
    count: int


@dataclass(frozen=True)
class ImageRecord:
    source_split: str
    source_image: Path
    source_label: Path
    width: int
    height: int
    annotations: tuple[Annotation, ...]


def load_classes(classes_file: Path) -> list[str]:
    if not classes_file.exists():
        raise FileNotFoundError(f"Class list not found: {classes_file}")

    classes = [
        line.strip()
        for line in classes_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not classes:
        raise ValueError(f"Class list is empty: {classes_file}")
    if len(classes) != len(set(classes)):
        duplicates = [name for name, count in Counter(classes).items() if count > 1]
        raise ValueError(f"Duplicate class names in {classes_file}: {duplicates}")
    return classes


def build_source_splits(source_root: Path) -> dict[str, SourceSplit]:
    return {
        "train": SourceSplit(
            name="train",
            image_dir=source_root / "Locount_ImagesTrain" / "Locount_ImagesTrain",
            label_dir=source_root / "Locount_GtTxtsTrain" / "Locount_GtTxtsTrain",
        ),
        "test": SourceSplit(
            name="test",
            image_dir=source_root / "Locount_ImagesTest" / "Locount_ImagesTest",
            label_dir=source_root / "Locount_GtTxtsTest" / "Locount_GtTxtsTest",
        ),
    }


def require_source_layout(splits: dict[str, SourceSplit]) -> None:
    missing = []
    for split in splits.values():
        if not split.image_dir.exists():
            missing.append(str(split.image_dir))
        if not split.label_dir.exists():
            missing.append(str(split.label_dir))
    if missing:
        raise FileNotFoundError("Missing source dataset paths:\n" + "\n".join(missing))


def iter_label_files(label_dir: Path) -> Iterable[Path]:
    yield from sorted(label_dir.glob("*.txt"))


def find_image_for_stem(image_dir: Path, stem: str) -> Path | None:
    for suffix in IMAGE_EXTENSIONS:
        image_path = image_dir / f"{stem}{suffix}"
        if image_path.exists():
            return image_path
    return None


def parse_annotation_line(line: str, label_file: Path, line_number: int) -> Annotation:
    parts = [part.strip() for part in line.split(",")]
    if len(parts) != 6:
        raise ValueError(f"Invalid annotation at {label_file}:{line_number}: {line}")

    x1, y1, x2, y2, label, count = parts
    left = min(float(x1), float(x2))
    top = min(float(y1), float(y2))
    right = max(float(x1), float(x2))
    bottom = max(float(y1), float(y2))
    count_i = int(count)
    if count_i < 1:
        raise ValueError(f"Invalid count at {label_file}:{line_number}: {count_i}")

    return Annotation(
        x1=left,
        y1=top,
        x2=right,
        y2=bottom,
        label=label,
        count=count_i,
    )


def clip(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def convert_box_to_yolo(annotation: Annotation, image_width: int, image_height: int) -> tuple[float, float, float, float]:
    left = clip(annotation.x1, 0.0, float(image_width))
    top = clip(annotation.y1, 0.0, float(image_height))
    right = clip(annotation.x2, 0.0, float(image_width))
    bottom = clip(annotation.y2, 0.0, float(image_height))

    box_width = max(0.0, right - left)
    box_height = max(0.0, bottom - top)
    center_x = left + box_width / 2.0
    center_y = top + box_height / 2.0

    return (
        center_x / image_width,
        center_y / image_height,
        box_width / image_width,
        box_height / image_height,
    )


def annotation_key(annotation: Annotation) -> tuple:
    return (
        annotation.label,
        int(round(annotation.x1)),
        int(round(annotation.y1)),
        int(round(annotation.x2)),
        int(round(annotation.y2)),
        annotation.count,
    )


def load_source_records(source_split: SourceSplit, retained_classes: set[str]) -> tuple[list[ImageRecord], dict]:
    records: list[ImageRecord] = []
    stats = Counter()

    label_files = list(iter_label_files(source_split.label_dir))
    for label_file in tqdm(label_files, desc=f"Reading source {source_split.name}", unit="file"):
        stats["label_files"] += 1
        image_path = find_image_for_stem(source_split.image_dir, label_file.stem)
        if image_path is None:
            stats["missing_images"] += 1
            continue

        try:
            with Image.open(image_path) as image:
                image_width, image_height = image.size
        except Exception:
            stats["unreadable_images"] += 1
            continue

        annotations: list[Annotation] = []
        seen_annotations: set[tuple] = set()
        for line_number, raw_line in enumerate(label_file.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                annotation = parse_annotation_line(line, label_file, line_number)
            except ValueError:
                stats["invalid_annotation_lines"] += 1
                continue

            if annotation.label not in retained_classes:
                stats["filtered_boxes"] += 1
                continue

            _x_center, _y_center, width, height = convert_box_to_yolo(
                annotation,
                image_width,
                image_height,
            )
            if width <= 0.0 or height <= 0.0:
                stats["invalid_boxes"] += 1
                continue

            key = annotation_key(annotation)
            if key in seen_annotations:
                stats["duplicate_boxes"] += 1
                continue

            seen_annotations.add(key)
            annotations.append(annotation)

        if not annotations:
            stats["skipped_images_without_retained_boxes"] += 1
            continue

        records.append(
            ImageRecord(
                source_split=source_split.name,
                source_image=image_path,
                source_label=label_file,
                width=image_width,
                height=image_height,
                annotations=tuple(annotations),
            )
        )
        stats["kept_images"] += 1
        stats["kept_boxes"] += len(annotations)

    return records, dict(stats)


def record_class_counts(record: ImageRecord) -> Counter[str]:
    return Counter(annotation.label for annotation in record.annotations)


def class_counts(records: Sequence[ImageRecord]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in records:
        counts.update(record_class_counts(record))
    return counts


def find_movable_record(
    records: Sequence[ImageRecord],
    source_counts: Counter[str],
    required_class: str,
) -> ImageRecord | None:
    candidates = [
        record
        for record in records
        if any(annotation.label == required_class for annotation in record.annotations)
    ]
    candidates.sort(key=lambda record: (len(record_class_counts(record)), len(record.annotations)))

    for record in candidates:
        removed_counts = record_class_counts(record)
        if all(source_counts[label] - amount > 0 for label, amount in removed_counts.items()):
            return record
    return None


def split_train_val(
    records: Sequence[ImageRecord],
    class_names: Sequence[str],
    val_ratio: float,
    seed: int,
) -> tuple[list[ImageRecord], list[ImageRecord]]:
    if not 0.0 < val_ratio < 1.0:
        raise ValueError("--val-ratio must be between 0 and 1")

    shuffled = list(records)
    random.Random(seed).shuffle(shuffled)
    val_size = max(1, round(len(shuffled) * val_ratio))
    val_records = shuffled[:val_size]
    train_records = shuffled[val_size:]

    max_moves = len(class_names) * 4
    for _ in range(max_moves):
        train_counts = class_counts(train_records)
        val_counts = class_counts(val_records)
        missing_in_train = [name for name in class_names if train_counts[name] == 0]
        missing_in_val = [name for name in class_names if val_counts[name] == 0]

        if not missing_in_train and not missing_in_val:
            return train_records, val_records

        moved = False
        if missing_in_val:
            class_name = missing_in_val[0]
            candidate = find_movable_record(train_records, train_counts, class_name)
            if candidate:
                train_records.remove(candidate)
                val_records.append(candidate)
                moved = True
        elif missing_in_train:
            class_name = missing_in_train[0]
            candidate = find_movable_record(val_records, val_counts, class_name)
            if candidate:
                val_records.remove(candidate)
                train_records.append(candidate)
                moved = True

        if not moved:
            raise RuntimeError(
                "Could not enforce class coverage for train/val split. "
                f"Missing in train: {missing_in_train}; missing in val: {missing_in_val}"
            )

    train_counts = class_counts(train_records)
    val_counts = class_counts(val_records)
    missing_in_train = [name for name in class_names if train_counts[name] == 0]
    missing_in_val = [name for name in class_names if val_counts[name] == 0]
    if missing_in_train or missing_in_val:
        raise RuntimeError(
            "Class coverage enforcement did not converge. "
            f"Missing in train: {missing_in_train}; missing in val: {missing_in_val}"
        )

    return train_records, val_records


def ensure_empty_or_force(target_root: Path, force: bool) -> None:
    if not target_root.exists():
        return
    if not any(target_root.iterdir()):
        return
    if not force:
        raise FileExistsError(
            f"Target dataset already exists and is not empty: {target_root}. "
            "Delete it first or rerun with --force."
        )
    shutil.rmtree(target_root)


def ensure_split_dirs(target_root: Path, splits: Iterable[str]) -> None:
    for split in splits:
        (target_root / split / "images").mkdir(parents=True, exist_ok=True)
        (target_root / split / "labels").mkdir(parents=True, exist_ok=True)


def transfer_image(source: Path, target: Path, image_mode: str) -> str:
    if target.exists():
        return "exists"
    if not source.exists():
        raise FileNotFoundError(f"Source image missing during transfer: {source}")

    if image_mode == "move":
        shutil.move(str(source), str(target))
        return "moved"
    if image_mode == "copy":
        shutil.copy2(source, target)
        return "copied"
    if image_mode == "hardlink":
        try:
            os.link(source, target)
            return "hardlinked"
        except OSError:
            shutil.copy2(source, target)
            return "copied"

    raise ValueError(f"Unsupported image mode: {image_mode}")


def write_split(
    *,
    split_name: str,
    records: Sequence[ImageRecord],
    target_root: Path,
    class_to_id: dict[str, int],
    image_mode: str,
) -> tuple[dict, list[dict]]:
    split_root = target_root / split_name
    images_dir = split_root / "images"
    labels_dir = split_root / "labels"
    counts_csv_path = split_root / "counts.csv"
    manifest_rows: list[dict] = []

    stats = {
        "images": 0,
        "boxes": 0,
        "class_box_counts": Counter(),
        "count_distribution": Counter(),
        "transfer_results": Counter(),
    }

    with counts_csv_path.open("w", encoding="utf-8", newline="") as counts_file:
        writer = csv.writer(counts_file)
        writer.writerow(["image", "class_id", "class_name", "count", "x1", "y1", "x2", "y2"])

        for index, record in enumerate(tqdm(records, desc=f"Writing {split_name}", unit="img"), start=1):
            target_stem = f"{split_name}_{index:06d}"
            target_image_name = f"{target_stem}{record.source_image.suffix.lower()}"
            target_label_name = f"{target_stem}.txt"
            target_image = images_dir / target_image_name
            target_label = labels_dir / target_label_name

            yolo_lines: list[str] = []
            for annotation in record.annotations:
                x_center, y_center, width, height = convert_box_to_yolo(
                    annotation,
                    record.width,
                    record.height,
                )
                class_id = class_to_id[annotation.label]
                yolo_lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n")
                writer.writerow(
                    [
                        target_image_name,
                        class_id,
                        annotation.label,
                        annotation.count,
                        int(round(annotation.x1)),
                        int(round(annotation.y1)),
                        int(round(annotation.x2)),
                        int(round(annotation.y2)),
                    ]
                )
                stats["boxes"] += 1
                stats["class_box_counts"][annotation.label] += 1
                stats["count_distribution"][annotation.count] += 1

            target_label.write_text("".join(yolo_lines), encoding="utf-8")
            transfer_result = transfer_image(record.source_image, target_image, image_mode)
            stats["transfer_results"][transfer_result] += 1
            stats["images"] += 1

            manifest_rows.append(
                {
                    "split": split_name,
                    "source_split": record.source_split,
                    "source_image": str(record.source_image),
                    "source_label": str(record.source_label),
                    "target_image": str(target_image),
                    "target_label": str(target_label),
                    "boxes": len(record.annotations),
                    "classes": ";".join(sorted(record_class_counts(record))),
                }
            )

    stats["class_box_counts"] = dict(sorted(stats["class_box_counts"].items()))
    stats["count_distribution"] = dict(sorted(stats["count_distribution"].items()))
    stats["transfer_results"] = dict(sorted(stats["transfer_results"].items()))
    return stats, manifest_rows


def write_classes_file(target_root: Path, class_names: Sequence[str]) -> None:
    (target_root / "classes.txt").write_text("\n".join(class_names) + "\n", encoding="utf-8")


def write_data_yaml(target_root: Path, class_names: Sequence[str]) -> None:
    yaml_text = "\n".join(
        [
            "# Auto-generated by prepare_locount_tvt_dataset.py",
            f"path: {target_root.resolve().as_posix()}",
            "train: train/images",
            "val: val/images",
            "test: test/images",
            f"nc: {len(class_names)}",
            f"names: {list(class_names)}",
            "",
        ]
    )
    (target_root / "data.yaml").write_text(yaml_text, encoding="utf-8")


def write_manifest(target_root: Path, manifest_rows: Sequence[dict]) -> None:
    manifest_path = target_root / "dataset_manifest.csv"
    fieldnames = [
        "split",
        "source_split",
        "source_image",
        "source_label",
        "target_image",
        "target_label",
        "boxes",
        "classes",
    ]
    with manifest_path.open("w", encoding="utf-8", newline="") as manifest_file:
        writer = csv.DictWriter(manifest_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)


def write_stats(
    target_root: Path,
    *,
    class_names: Sequence[str],
    source_stats: dict,
    split_stats: dict,
    seed: int,
    val_ratio: float,
    source_root: Path,
) -> None:
    payload = {
        "source_root": str(source_root),
        "target_root": str(target_root),
        "seed": seed,
        "val_ratio": val_ratio,
        "class_count": len(class_names),
        "classes": list(class_names),
        "source_stats": source_stats,
        "splits": split_stats,
    }
    (target_root / "dataset_stats.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def summarize_split(records: Sequence[ImageRecord], class_names: Sequence[str]) -> dict:
    counts = class_counts(records)
    return {
        "images": len(records),
        "boxes": sum(counts.values()),
        "classes_present": sum(1 for name in class_names if counts[name] > 0),
        "missing_classes": [name for name in class_names if counts[name] == 0],
    }


def print_summary(summary: dict) -> None:
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the strict Locount 93-class train/val/test dataset.")
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--target-root", default=str(DEFAULT_TARGET_ROOT))
    parser.add_argument("--classes-file", default=str(DEFAULT_CLASSES_FILE))
    parser.add_argument("--seed", type=int, default=20260515)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--image-mode", choices=["move", "copy", "hardlink"], default="move")
    parser.add_argument("--dry-run", action="store_true", help="Only read source data and print planned split stats.")
    parser.add_argument("--force", action="store_true", help="Delete a non-empty target root before writing.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    source_root = Path(args.source_root).resolve()
    target_root = Path(args.target_root).resolve()
    classes_file = Path(args.classes_file).resolve()

    class_names = load_classes(classes_file)
    class_to_id = {name: index for index, name in enumerate(class_names)}
    source_splits = build_source_splits(source_root)
    require_source_layout(source_splits)

    print("=" * 72)
    print("Locount strict train/val/test preparation")
    print("=" * 72)
    print(f"Source     : {source_root}")
    print(f"Target     : {target_root}")
    print(f"Classes    : {classes_file} ({len(class_names)})")
    print(f"Split seed : {args.seed}")
    print(f"Val ratio  : {args.val_ratio}")
    print(f"Image mode : {args.image_mode}")
    print(f"Dry run    : {args.dry_run}")

    train_source_records, train_source_stats = load_source_records(source_splits["train"], set(class_names))
    test_records, test_source_stats = load_source_records(source_splits["test"], set(class_names))
    train_records, val_records = split_train_val(
        train_source_records,
        class_names,
        val_ratio=args.val_ratio,
        seed=args.seed,
    )

    planned_summary = {
        "train": summarize_split(train_records, class_names),
        "val": summarize_split(val_records, class_names),
        "test": summarize_split(test_records, class_names),
        "source_train": train_source_stats,
        "source_test": test_source_stats,
    }
    print("\nPlanned dataset summary:")
    print_summary(planned_summary)

    if args.dry_run:
        return 0

    ensure_empty_or_force(target_root, force=args.force)
    target_root.mkdir(parents=True, exist_ok=True)
    ensure_split_dirs(target_root, ["train", "val", "test"])

    split_records = {
        "train": train_records,
        "val": val_records,
        "test": test_records,
    }
    split_stats = {}
    manifest_rows: list[dict] = []
    for split_name, records in split_records.items():
        stats, rows = write_split(
            split_name=split_name,
            records=records,
            target_root=target_root,
            class_to_id=class_to_id,
            image_mode=args.image_mode,
        )
        split_stats[split_name] = stats
        manifest_rows.extend(rows)

    write_classes_file(target_root, class_names)
    write_data_yaml(target_root, class_names)
    write_manifest(target_root, manifest_rows)
    write_stats(
        target_root,
        class_names=class_names,
        source_stats={"train": train_source_stats, "test": test_source_stats},
        split_stats=split_stats,
        seed=args.seed,
        val_ratio=args.val_ratio,
        source_root=source_root,
    )

    print("\n[OK] Dataset prepared.")
    print(f"[OK] data.yaml: {target_root / 'data.yaml'}")
    print(f"[OK] manifest : {target_root / 'dataset_manifest.csv'}")
    print(f"[OK] stats    : {target_root / 'dataset_stats.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
