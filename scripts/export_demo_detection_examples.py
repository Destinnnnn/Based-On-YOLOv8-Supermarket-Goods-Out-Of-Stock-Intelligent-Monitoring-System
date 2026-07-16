#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import random
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.demo_seed_service import TRANSLATED_ITEM_NAMES_BY_LABEL


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/NotoSansSC-VF.ttf"),
    Path("C:/Windows/Fonts/SourceHanSansCN-Normal.ttf"),
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("C:/Windows/Fonts/simsun.ttc"),
)


@dataclass(frozen=True)
class Box:
    image: str
    class_id: int
    class_name: str
    count: int
    xyxy: tuple[float, float, float, float]
    confidence: float | None = None


@dataclass(frozen=True)
class VerifiedBox:
    prediction: Box
    annotation: Box
    iou: float
    area_ratio: float
    count_bucket: str
    size_bucket: str


@dataclass
class ImageCandidate:
    image: str
    source_image: Path
    candidate_path: Path
    verified_boxes: list[VerifiedBox]
    total_gt_count: int
    matched_gt_count: int
    full_image_match: bool
    primary_count_bucket: str
    primary_size_bucket: str
    score: float
    selected: bool = False
    final_path: Path | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export defense-ready detection examples with verified class labels "
            "and per-box counts."
        )
    )
    parser.add_argument("--images-dir", type=Path, default=PROJECT_ROOT / "datasets" / "test" / "images")
    parser.add_argument("--counts-csv", type=Path, default=PROJECT_ROOT / "datasets" / "test" / "counts.csv")
    parser.add_argument("--classes-path", type=Path, default=PROJECT_ROOT / "datasets" / "classes.txt")
    parser.add_argument(
        "--prediction-csv",
        type=Path,
        default=PROJECT_ROOT / "runtime" / "count_export" / "224_baseline" / "test_predictions.csv",
        help=(
            "Use an existing YOLO+Count prediction CSV. Pass an empty string to "
            "run the current model instead."
        ),
    )
    parser.add_argument("--model", type=Path, default=PROJECT_ROOT / "models" / "best.pt")
    parser.add_argument("--count-weights", type=Path, default=PROJECT_ROOT / "weights" / "count_best.pt")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "thesis_assets" / "demo_detection_examples_all_boxes",
    )
    parser.add_argument("--seed", type=int, default=20260519)
    parser.add_argument("--target-final", type=int, default=50)
    parser.add_argument("--candidate-target", type=int, default=240)
    parser.add_argument("--max-images", type=int, default=2500)
    parser.add_argument(
        "--max-boxes-per-image",
        type=int,
        default=0,
        help="Maximum verified boxes to draw per image. Use 0 for no cap.",
    )
    parser.add_argument(
        "--require-full-image-match",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Only keep images where every count annotation is matched by class, IoU, and count.",
    )
    parser.add_argument("--iou-threshold", type=float, default=0.70)
    parser.add_argument("--conf-threshold", type=float, default=0.15)
    parser.add_argument("--min-final-conf", type=float, default=0.0)
    parser.add_argument("--font-size", type=int, default=30)
    parser.add_argument("--thumb-width", type=int, default=360)
    parser.add_argument("--clean", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def load_classes(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_counts_csv(path: Path) -> dict[str, list[Box]]:
    annotations: dict[str, list[Box]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            image = row["image"]
            box = Box(
                image=image,
                class_id=int(row["class_id"]),
                class_name=row["class_name"],
                count=int(float(row["count"])),
                xyxy=(
                    float(row["x1"]),
                    float(row["y1"]),
                    float(row["x2"]),
                    float(row["y2"]),
                ),
            )
            annotations.setdefault(image, []).append(box)
    return annotations


def parse_prediction_csv(path: Path, classes: list[str]) -> dict[str, list[Box]]:
    predictions: dict[str, list[Box]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            error = int(float(row.get("error", "0")))
            if error != 0:
                continue
            image = row["image"]
            class_id = int(row["class_id"])
            xyxy = ast.literal_eval(row["xyxy"])
            count = int(float(row.get("count_pred", row.get("count", 1))))
            box = Box(
                image=image,
                class_id=class_id,
                class_name=classes[class_id],
                count=count,
                xyxy=tuple(float(value) for value in xyxy),
            )
            predictions.setdefault(image, []).append(box)
    return predictions


def run_live_predictions(
    image_paths: Iterable[Path],
    *,
    model_path: Path,
    count_weights: Path,
    conf_threshold: float,
) -> dict[str, list[Box]]:
    import torch
    from ultralytics import YOLO

    from count_module import CountPredictor

    model = YOLO(str(model_path))
    counter = CountPredictor(count_weights, device="cuda" if torch.cuda.is_available() else "cpu")
    predictions: dict[str, list[Box]] = {}

    for image_path in image_paths:
        result = model(str(image_path), verbose=False, conf=conf_threshold)[0]
        detections: list[dict[str, Any]] = []
        for raw_box in result.boxes:
            x1, y1, x2, y2 = raw_box.xyxy[0].cpu().tolist()
            class_id = int(raw_box.cls[0].cpu().item())
            detections.append(
                {
                    "xyxy": [x1, y1, x2, y2],
                    "class_id": class_id,
                    "conf": float(raw_box.conf[0].cpu().item()),
                }
            )

        counted = counter.predict(image_path, detections, batch_size=64)
        boxes = [
            Box(
                image=image_path.name,
                class_id=int(det["class_id"]),
                class_name=model.names[int(det["class_id"])],
                count=int(det["count"]),
                xyxy=tuple(float(value) for value in det["xyxy"]),
                confidence=float(det.get("conf", 0.0)),
            )
            for det in counted
        ]
        predictions[image_path.name] = boxes
    return predictions


def box_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih
    if intersection <= 0:
        return 0.0

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def count_bucket(count: int) -> str:
    if count <= 1:
        return "single"
    if count <= 6:
        return "medium_count"
    return "multi_count"


def size_bucket(area_ratio: float) -> str:
    if area_ratio < 0.035:
        return "small_target"
    if area_ratio >= 0.12:
        return "large_target"
    return "mid_target"


def match_predictions(
    predictions: list[Box],
    annotations: list[Box],
    *,
    image_size: tuple[int, int],
    iou_threshold: float,
    max_boxes: int,
    min_conf: float,
) -> list[VerifiedBox]:
    unused_annotations = set(range(len(annotations)))
    verified: list[VerifiedBox] = []
    sorted_predictions = sorted(
        predictions,
        key=lambda box: (
            box.confidence if box.confidence is not None else 1.0,
            box.count,
            box_area(box.xyxy),
        ),
        reverse=True,
    )

    for prediction in sorted_predictions:
        if prediction.confidence is not None and prediction.confidence < min_conf:
            continue

        best_index: int | None = None
        best_iou = 0.0
        for index in unused_annotations:
            annotation = annotations[index]
            if prediction.class_id != annotation.class_id:
                continue
            if prediction.count != annotation.count:
                continue
            iou = box_iou(prediction.xyxy, annotation.xyxy)
            if iou > best_iou:
                best_iou = iou
                best_index = index

        if best_index is None or best_iou < iou_threshold:
            continue

        unused_annotations.remove(best_index)
        area_ratio = box_area(prediction.xyxy) / float(image_size[0] * image_size[1])
        verified.append(
            VerifiedBox(
                prediction=prediction,
                annotation=annotations[best_index],
                iou=best_iou,
                area_ratio=area_ratio,
                count_bucket=count_bucket(prediction.count),
                size_bucket=size_bucket(area_ratio),
            )
        )
        if max_boxes > 0 and len(verified) >= max_boxes:
            break

    return verified


def box_area(xyxy: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = xyxy
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def resolve_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in DEFAULT_FONT_CANDIDATES:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def class_color(class_id: int) -> tuple[int, int, int]:
    palette = (
        (24, 121, 191),
        (41, 157, 143),
        (230, 126, 34),
        (180, 70, 90),
        (88, 129, 87),
        (108, 92, 231),
        (201, 76, 76),
        (0, 137, 123),
    )
    return palette[class_id % len(palette)]


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def label_text(box: Box) -> str:
    zh_name = TRANSLATED_ITEM_NAMES_BY_LABEL.get(box.class_name, box.class_name)
    confidence = "" if box.confidence is None else f" {box.confidence:.2f}"
    return f"{zh_name} / {box.class_name}  count={box.count}{confidence}"


def draw_candidate(
    source_image: Path,
    output_path: Path,
    verified_boxes: list[VerifiedBox],
    *,
    font: ImageFont.ImageFont,
) -> None:
    image = Image.open(source_image).convert("RGB")
    draw = ImageDraw.Draw(image)

    for verified in verified_boxes:
        box = verified.prediction
        x1, y1, x2, y2 = box.xyxy
        color = class_color(box.class_id)
        line_width = max(3, int(min(image.size) / 360))
        draw.rectangle((x1, y1, x2, y2), outline=color, width=line_width)

        text = label_text(box)
        text_w, text_h = text_size(draw, text, font)
        pad_x = 8
        pad_y = 5
        label_x = max(0, int(x1))
        label_y = max(0, int(y1) - text_h - pad_y * 2 - 2)
        if label_y <= 2:
            label_y = min(image.height - text_h - pad_y * 2, int(y1) + 2)
        background = (
            label_x,
            label_y,
            min(image.width - 1, label_x + text_w + pad_x * 2),
            min(image.height - 1, label_y + text_h + pad_y * 2),
        )
        draw.rectangle(background, fill=color)
        draw.text((label_x + pad_x, label_y + pad_y), text, fill=(255, 255, 255), font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=94)


def clear_generated_dir(path: Path) -> None:
    resolved = path.resolve()
    project = PROJECT_ROOT.resolve()
    if project not in resolved.parents and resolved != project:
        raise ValueError(f"Refusing to clean directory outside project: {resolved}")
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def profile_priority(candidate: ImageCandidate) -> tuple[str, str]:
    return candidate.primary_count_bucket, candidate.primary_size_bucket


def primary_count_bucket(boxes: list[VerifiedBox]) -> str:
    buckets = [box.count_bucket for box in boxes]
    if "multi_count" in buckets:
        return "multi_count"
    if "medium_count" in buckets:
        return "medium_count"
    return "single"


def primary_size_bucket(boxes: list[VerifiedBox]) -> str:
    buckets = [box.size_bucket for box in boxes]
    if "small_target" in buckets:
        return "small_target"
    if "large_target" in buckets:
        return "large_target"
    return "mid_target"


def candidate_score(boxes: list[VerifiedBox]) -> float:
    if not boxes:
        return 0.0
    avg_iou = sum(box.iou for box in boxes) / len(boxes)
    avg_conf = [
        box.prediction.confidence
        for box in boxes
        if box.prediction.confidence is not None
    ]
    conf_score = sum(avg_conf) / len(avg_conf) if avg_conf else 0.85
    bucket_bonus = len({box.count_bucket for box in boxes}) * 0.2
    return len(boxes) + avg_iou + conf_score + bucket_bonus


def select_final(candidates: list[ImageCandidate], target: int) -> list[ImageCandidate]:
    selected: list[ImageCandidate] = []
    count_targets = {"single": 12, "medium_count": 16, "multi_count": 12}
    size_targets = {"small_target": 12, "mid_target": 10, "large_target": 12}
    class_counts: dict[str, int] = {}
    count_seen = {key: 0 for key in count_targets}
    size_seen = {key: 0 for key in size_targets}

    remaining = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
    while remaining and len(selected) < target:
        best: ImageCandidate | None = None
        best_score = -999.0
        for candidate in remaining:
            classes = {box.prediction.class_name for box in candidate.verified_boxes}
            repeat_penalty = sum(max(0, class_counts.get(name, 0) - 4) for name in classes)
            count_deficit = max(
                0,
                count_targets.get(candidate.primary_count_bucket, 0)
                - count_seen.get(candidate.primary_count_bucket, 0),
            )
            size_deficit = max(
                0,
                size_targets.get(candidate.primary_size_bucket, 0)
                - size_seen.get(candidate.primary_size_bucket, 0),
            )
            score = candidate.score + count_deficit * 1.5 + size_deficit - repeat_penalty * 0.8
            if score > best_score:
                best = candidate
                best_score = score

        if best is None:
            break

        remaining.remove(best)
        best.selected = True
        selected.append(best)
        count_seen[best.primary_count_bucket] = count_seen.get(best.primary_count_bucket, 0) + 1
        size_seen[best.primary_size_bucket] = size_seen.get(best.primary_size_bucket, 0) + 1
        for box in best.verified_boxes:
            class_counts[box.prediction.class_name] = class_counts.get(box.prediction.class_name, 0) + 1

    return selected


def write_index(path: Path, candidates: list[ImageCandidate]) -> None:
    fieldnames = [
        "selected",
        "image",
        "candidate_path",
        "final_path",
        "verified_box_count",
        "total_gt_count",
        "matched_gt_count",
        "full_image_match",
        "classes",
        "counts",
        "count_bucket",
        "size_bucket",
        "min_iou",
        "avg_iou",
        "min_confidence",
        "source_boxes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in candidates:
            boxes = candidate.verified_boxes
            confidences = [
                box.prediction.confidence
                for box in boxes
                if box.prediction.confidence is not None
            ]
            writer.writerow(
                {
                    "selected": "yes" if candidate.selected else "no",
                    "image": candidate.image,
                    "candidate_path": str(candidate.candidate_path),
                    "final_path": str(candidate.final_path or ""),
                    "verified_box_count": len(boxes),
                    "total_gt_count": candidate.total_gt_count,
                    "matched_gt_count": candidate.matched_gt_count,
                    "full_image_match": "yes" if candidate.full_image_match else "no",
                    "classes": "; ".join(sorted({box.prediction.class_name for box in boxes})),
                    "counts": "; ".join(str(box.prediction.count) for box in boxes),
                    "count_bucket": candidate.primary_count_bucket,
                    "size_bucket": candidate.primary_size_bucket,
                    "min_iou": f"{min(box.iou for box in boxes):.4f}",
                    "avg_iou": f"{sum(box.iou for box in boxes) / len(boxes):.4f}",
                    "min_confidence": "" if not confidences else f"{min(confidences):.4f}",
                    "source_boxes": " | ".join(
                        f"{box.prediction.class_name}:count={box.prediction.count}:"
                        f"iou={box.iou:.3f}:area={box.area_ratio:.4f}"
                        for box in boxes
                    ),
                }
            )


def make_contact_sheet(path: Path, selected: list[ImageCandidate], thumb_width: int) -> None:
    if not selected:
        return

    columns = 5
    padding = 14
    label_height = 34
    thumbs: list[Image.Image] = []
    for index, candidate in enumerate(selected, start=1):
        image = Image.open(candidate.final_path or candidate.candidate_path).convert("RGB")
        ratio = thumb_width / image.width
        thumb_height = int(image.height * ratio)
        image = image.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (thumb_width, thumb_height + label_height), (255, 255, 255))
        canvas.paste(image, (0, label_height))
        draw = ImageDraw.Draw(canvas)
        draw.text((6, 6), f"{index:02d}  {candidate.primary_count_bucket} / {candidate.primary_size_bucket}", fill=(20, 20, 20))
        thumbs.append(canvas)

    rows = (len(thumbs) + columns - 1) // columns
    cell_width = thumb_width + padding
    cell_height = max(thumb.height for thumb in thumbs) + padding
    sheet = Image.new("RGB", (columns * cell_width + padding, rows * cell_height + padding), (245, 245, 245))
    for index, thumb in enumerate(thumbs):
        row = index // columns
        col = index % columns
        sheet.paste(thumb, (padding + col * cell_width, padding + row * cell_height))
    sheet.save(path, quality=92)


def write_summary(path: Path, selected: list[ImageCandidate], candidates: list[ImageCandidate]) -> None:
    def bucket_counts(values: Iterable[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        return counts

    selected_count_buckets = bucket_counts(candidate.primary_count_bucket for candidate in selected)
    selected_size_buckets = bucket_counts(candidate.primary_size_bucket for candidate in selected)
    selected_classes = bucket_counts(
        box.prediction.class_name for candidate in selected for box in candidate.verified_boxes
    )
    full_match_candidates = sum(1 for candidate in candidates if candidate.full_image_match)
    full_match_selected = sum(1 for candidate in selected if candidate.full_image_match)
    total_drawn_boxes = sum(len(candidate.verified_boxes) for candidate in selected)
    max_drawn_boxes = max((len(candidate.verified_boxes) for candidate in selected), default=0)
    top_classes = sorted(selected_classes.items(), key=lambda item: item[1], reverse=True)[:15]
    lines = [
        "# Demo Detection Example Export",
        "",
        f"- Candidate images: {len(candidates)}",
        f"- Final selected images: {len(selected)}",
        f"- Full-image matched candidates: {full_match_candidates}",
        f"- Full-image matched selected images: {full_match_selected}",
        f"- Total drawn boxes in final set: {total_drawn_boxes}",
        f"- Maximum drawn boxes in one final image: {max_drawn_boxes}",
        f"- Count buckets: {selected_count_buckets}",
        f"- Size buckets: {selected_size_buckets}",
        f"- Top classes: {top_classes}",
        "",
        "All drawn boxes were automatically matched against test count annotations by class, IoU, and count.",
        "The default export has no six-box-per-image cap. With --require-full-image-match, every test annotation in a selected image must be matched before the image is kept.",
        "Final images should still be visually reviewed before being used in slides.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_final_images(selected: list[ImageCandidate], final_dir: Path) -> None:
    final_dir.mkdir(parents=True, exist_ok=True)
    for index, candidate in enumerate(selected, start=1):
        stem = Path(candidate.image).stem
        final_path = final_dir / (
            f"{index:02d}_{candidate.primary_count_bucket}_{candidate.primary_size_bucket}_{stem}.jpg"
        )
        shutil.copy2(candidate.candidate_path, final_path)
        candidate.final_path = final_path


def collect_image_paths(images_dir: Path) -> list[Path]:
    return sorted(path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    candidates_dir = output_dir / "candidates"
    final_dir = output_dir / "final_50"

    if args.clean:
        clear_generated_dir(output_dir)
    candidates_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    random.seed(args.seed)
    classes = load_classes(args.classes_path)
    annotations = read_counts_csv(args.counts_csv)
    all_image_paths = collect_image_paths(args.images_dir)
    random.shuffle(all_image_paths)
    selected_image_paths = all_image_paths[: args.max_images]

    if args.prediction_csv and str(args.prediction_csv).strip():
        predictions = parse_prediction_csv(args.prediction_csv, classes)
    else:
        predictions = run_live_predictions(
            selected_image_paths,
            model_path=args.model,
            count_weights=args.count_weights,
            conf_threshold=args.conf_threshold,
        )

    font = resolve_font(args.font_size)
    candidates: list[ImageCandidate] = []
    for image_path in selected_image_paths:
        image_predictions = predictions.get(image_path.name, [])
        image_annotations = annotations.get(image_path.name, [])
        if not image_predictions or not image_annotations:
            continue

        with Image.open(image_path) as image:
            verified_boxes = match_predictions(
                image_predictions,
                image_annotations,
                image_size=image.size,
                iou_threshold=args.iou_threshold,
                max_boxes=args.max_boxes_per_image,
                min_conf=args.min_final_conf,
            )
        if not verified_boxes:
            continue
        total_gt_count = len(image_annotations)
        matched_gt_count = len(verified_boxes)
        full_image_match = matched_gt_count == total_gt_count
        if args.require_full_image_match and not full_image_match:
            continue

        count_profile = primary_count_bucket(verified_boxes)
        size_profile = primary_size_bucket(verified_boxes)
        candidate_path = candidates_dir / f"{len(candidates) + 1:04d}_{count_profile}_{size_profile}_{image_path.name}"
        draw_candidate(image_path, candidate_path, verified_boxes, font=font)
        candidates.append(
            ImageCandidate(
                image=image_path.name,
                source_image=image_path,
                candidate_path=candidate_path,
                verified_boxes=verified_boxes,
                total_gt_count=total_gt_count,
                matched_gt_count=matched_gt_count,
                full_image_match=full_image_match,
                primary_count_bucket=count_profile,
                primary_size_bucket=size_profile,
                score=candidate_score(verified_boxes),
            )
        )
        if len(candidates) >= args.candidate_target:
            break

    selected = select_final(candidates, args.target_final)
    copy_final_images(selected, final_dir)
    write_index(output_dir / "index.csv", candidates)
    make_contact_sheet(output_dir / "contact_sheet.jpg", selected, args.thumb_width)
    write_summary(output_dir / "summary.md", selected, candidates)

    print(f"Candidates: {len(candidates)}")
    print(f"Final selected: {len(selected)}")
    print(f"Output: {output_dir}")
    if len(selected) < args.target_final:
        print(
            "WARNING: final selection is below target. Lower thresholds or "
            "increase --candidate-target/--max-images if more examples are needed."
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
