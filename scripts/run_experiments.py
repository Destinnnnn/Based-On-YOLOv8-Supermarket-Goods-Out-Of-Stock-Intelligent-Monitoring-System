from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

import httpx
import psutil
import torch
import websockets
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from train_yolov8 import prepare_ultralytics_runtime
from app.db.base_class import Base
from app.models.item import Item
from app.models.label_mapping import LabelMapping
from app.models.system_settings import SystemSettings
from app.services.stock_service import StockService

DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "best.pt"
DEFAULT_DATA_YAML = PROJECT_ROOT / "datasets" / "data.yaml"
DEFAULT_STABILITY_IMAGES_DIR = (
    PROJECT_ROOT / "datasets" / "test" / "images"
)
DEFAULT_EXPERIMENT_OUTPUT_DIR = PROJECT_ROOT / "thesis_assets" / "experiments"
DEFAULT_PARAM_OUTPUT_DIR = PROJECT_ROOT / "runtime" / "param_sensitivity"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MB = 1024 * 1024

THRESHOLD_GRID = [
    (0.10, 0.60),
    (0.15, 0.60),
    (0.20, 0.60),
    (0.15, 0.50),
    (0.15, 0.70),
]

CONFIRMATION_GRID = [
    (1, 1),
    (2, 3),
    (3, 5),
]

BASELINE_CONF = 0.15
BASELINE_IOU = 0.60
MAP5095_RECOMMENDATION_TOLERANCE = 0.001


@dataclass
class ThresholdResult:
    conf: float
    iou: float
    precision: float | None
    recall: float | None
    map50: float | None
    map5095: float | None
    f1: float | None
    note: str = ""

    @property
    def key(self) -> str:
        return threshold_key(self.conf, self.iou)


@dataclass
class ConfirmationResult:
    presence_frames: int
    absence_frames: int
    presence_delay_frames: int
    absence_delay_frames: int
    note: str = ""


@dataclass
class ClientStats:
    client_id: str
    sent_frames: int = 0
    received_frames: int = 0
    disconnects: int = 0
    latencies_ms: list[float] | None = None

    def __post_init__(self) -> None:
        if self.latencies_ms is None:
            self.latencies_ms = []


@dataclass
class SamplePoint:
    elapsed_seconds: float
    backend_cpu_pct: float
    backend_rss_mb: float
    system_cpu_pct: float
    system_memory_pct: float


@dataclass
class ManagedBackend:
    process: subprocess.Popen
    stdout_handle: Any
    stderr_handle: Any


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_device() -> str | int:
    return 0 if torch.cuda.is_available() else "cpu"


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt(value: float | None, digits: int = 4) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def mean_or_zero(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * (pct / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    return ordered[lower] * (upper - rank) + ordered[upper] * (rank - lower)


def markdown_table(headers: list[str], rows: list[dict[str, Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        values = [str(row.get(header, "")) for header in headers]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def output_path(output_dir: Path, base_name: str, suffix: str, tag: str | None) -> Path:
    if tag:
        return output_dir / f"{base_name}_{tag}{suffix}"
    return output_dir / f"{base_name}{suffix}"


def threshold_key(conf: float, iou: float) -> str:
    return f"{conf:.2f}_{iou:.2f}"


def threshold_result_to_csv_row(row: ThresholdResult) -> dict[str, Any]:
    return {
        "experiment_type": "threshold",
        "conf": fmt(row.conf, 2),
        "iou": fmt(row.iou, 2),
        "presence_frames": "",
        "absence_frames": "",
        "precision": fmt(row.precision, 5),
        "recall": fmt(row.recall, 5),
        "map50": fmt(row.map50, 5),
        "map5095": fmt(row.map5095, 5),
        "f1": fmt(row.f1, 5),
        "presence_delay_frames": "",
        "absence_delay_frames": "",
        "note": row.note,
    }


PARAMETER_CSV_FIELDS = [
    "experiment_type",
    "conf",
    "iou",
    "presence_frames",
    "absence_frames",
    "precision",
    "recall",
    "map50",
    "map5095",
    "f1",
    "presence_delay_frames",
    "absence_delay_frames",
    "note",
]


def load_partial_threshold_results(path: Path) -> dict[str, ThresholdResult]:
    if not path.exists():
        return {}

    rows: dict[str, ThresholdResult] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for csv_row in reader:
            if csv_row.get("experiment_type") != "threshold":
                continue
            conf = float(csv_row["conf"])
            iou = float(csv_row["iou"])
            rows[threshold_key(conf, iou)] = ThresholdResult(
                conf=conf,
                iou=iou,
                precision=to_float(csv_row.get("precision")),
                recall=to_float(csv_row.get("recall")),
                map50=to_float(csv_row.get("map50")),
                map5095=to_float(csv_row.get("map5095")),
                f1=to_float(csv_row.get("f1")),
                note=csv_row.get("note", ""),
            )
    return rows


def write_partial_threshold_results(path: Path, rows: list[ThresholdResult]) -> None:
    write_csv(
        path,
        [threshold_result_to_csv_row(row) for row in rows],
        PARAMETER_CSV_FIELDS,
    )


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@contextmanager
def validation_subset(data_yaml: Path, sample_size: int | None) -> Iterator[Path]:
    if sample_size is None:
        yield data_yaml
        return

    data = load_yaml(data_yaml)
    base_path = Path(data.get("path") or data_yaml.parent).resolve()
    val_entry = Path(str(data.get("val", "val/images")))
    images_dir = (base_path / val_entry).resolve()
    labels_dir = images_dir.parent / "labels"

    image_paths = sorted(
        path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not image_paths:
        raise FileNotFoundError(f"No validation images found in {images_dir}")

    if sample_size >= len(image_paths):
        yield data_yaml
        return

    scratch_root = ensure_dir(PROJECT_ROOT / "validation_runs" / "experiment_tmp")
    temp_dir = scratch_root / f"yolo_val_subset_{time.time_ns()}"
    temp_dir.mkdir(parents=True, exist_ok=False)

    try:
        subset_images = temp_dir / "val" / "images"
        subset_labels = temp_dir / "val" / "labels"
        subset_images.mkdir(parents=True, exist_ok=True)
        subset_labels.mkdir(parents=True, exist_ok=True)

        for image_path in image_paths[:sample_size]:
            shutil.copy2(image_path, subset_images / image_path.name)
            label_path = labels_dir / f"{image_path.stem}.txt"
            if label_path.exists():
                shutil.copy2(label_path, subset_labels / label_path.name)

        subset_yaml = temp_dir / "subset_data.yaml"
        subset_yaml.write_text(
            yaml.safe_dump(
                {
                    "path": str(temp_dir),
                    "train": "val/images",
                    "val": "val/images",
                    "nc": data.get("nc"),
                    "names": data.get("names"),
                },
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        yield subset_yaml
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def run_threshold_sweep(
    model_path: Path,
    data_yaml: Path,
    *,
    imgsz: int,
    batch: int,
    workers: int,
    sample_size: int | None,
    partial_csv: Path | None = None,
    progress_json: Path | None = None,
    resume: bool = False,
) -> list[ThresholdResult]:
    prepare_ultralytics_runtime()
    model = YOLO(str(model_path))
    completed = load_partial_threshold_results(partial_csv) if partial_csv and resume else {}
    results: list[ThresholdResult] = []

    for conf, iou in THRESHOLD_GRID:
        existing = completed.get(threshold_key(conf, iou))
        if existing:
            results.append(existing)

    with validation_subset(data_yaml, sample_size) as effective_data_yaml:
        for index, (conf, iou) in enumerate(THRESHOLD_GRID, start=1):
            if threshold_key(conf, iou) in completed:
                print(
                    f"[INFO] Skipping completed threshold {index}/{len(THRESHOLD_GRID)} "
                    f"conf={conf:.2f}, iou={iou:.2f}",
                    flush=True,
                )
                continue

            if progress_json:
                write_json(
                    progress_json,
                    {
                        "status": "running",
                        "current_index": index,
                        "total": len(THRESHOLD_GRID),
                        "current_conf": conf,
                        "current_iou": iou,
                        "completed": len(results),
                        "model": str(model_path),
                        "data": str(data_yaml),
                        "effective_data": str(effective_data_yaml),
                        "split": "val",
                        "imgsz": imgsz,
                        "batch": batch,
                        "workers": workers,
                        "sample_size": sample_size,
                        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    },
                )
            print(
                f"[INFO] Validating threshold {index}/{len(THRESHOLD_GRID)} "
                f"conf={conf:.2f}, iou={iou:.2f}, "
                f"imgsz={imgsz}, batch={batch}, data={effective_data_yaml}",
                flush=True,
            )
            started = time.perf_counter()
            metrics = model.val(
                data=str(effective_data_yaml),
                split="val",
                imgsz=imgsz,
                batch=batch,
                workers=workers,
                device=resolve_device(),
                conf=conf,
                iou=iou,
                plots=False,
                save=False,
                verbose=False,
            )
            metric_dict = getattr(metrics, "results_dict", {}) or {}
            precision = to_float(metric_dict.get("metrics/precision(B)"))
            recall = to_float(metric_dict.get("metrics/recall(B)"))
            map50 = to_float(metric_dict.get("metrics/mAP50(B)"))
            map5095 = to_float(metric_dict.get("metrics/mAP50-95(B)"))
            f1 = None
            if precision is not None and recall is not None and (precision + recall) > 0:
                f1 = 2 * precision * recall / (precision + recall)

            elapsed = time.perf_counter() - started
            print(
                f"[INFO] Finished conf={conf:.2f}, iou={iou:.2f} in {elapsed:.1f}s: "
                f"P={fmt(precision, 5)}, R={fmt(recall, 5)}, "
                f"mAP50={fmt(map50, 5)}, mAP50-95={fmt(map5095, 5)}",
                flush=True,
            )
            result = ThresholdResult(
                conf=conf,
                iou=iou,
                precision=precision,
                recall=recall,
                map50=map50,
                map5095=map5095,
                f1=f1,
            )
            results.append(result)
            if partial_csv:
                ordered_results = sorted(
                    results,
                    key=lambda row: THRESHOLD_GRID.index((row.conf, row.iou)),
                )
                write_partial_threshold_results(partial_csv, ordered_results)
                print(f"[INFO] Partial threshold results written to {partial_csv}", flush=True)

    best = select_recommended_threshold(results)
    for row in results:
        if row is best:
            row.note = "Recommended"
        elif row.conf == BASELINE_CONF and row.iou == BASELINE_IOU:
            row.note = "Baseline"
        else:
            row.note = "Comparison"
    if partial_csv:
        ordered_results = sorted(
            results,
            key=lambda row: THRESHOLD_GRID.index((row.conf, row.iou)),
        )
        write_partial_threshold_results(partial_csv, ordered_results)
    if progress_json:
        write_json(
            progress_json,
            {
                "status": "threshold_sweep_complete",
                "completed": len(results),
                "total": len(THRESHOLD_GRID),
                "model": str(model_path),
                "data": str(data_yaml),
                "split": "val",
                "imgsz": imgsz,
                "batch": batch,
                "workers": workers,
                "sample_size": sample_size,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
    return results


def select_recommended_threshold(results: list[ThresholdResult]) -> ThresholdResult:
    metric_best = max(
        results,
        key=lambda row: (
            row.map5095 if row.map5095 is not None else -1.0,
            row.f1 if row.f1 is not None else -1.0,
        ),
    )
    baseline = next(
        row for row in results if row.conf == BASELINE_CONF and row.iou == BASELINE_IOU
    )
    if baseline.map5095 is not None and metric_best.map5095 is not None:
        if metric_best.map5095 - baseline.map5095 <= MAP5095_RECOMMENDATION_TOLERANCE:
            return baseline
    return metric_best


def build_confirmation_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    db.add(
        SystemSettings(
            id=1,
            default_item_threshold=10,
            stock_presence_confirmation_frames=2,
            stock_absence_confirmation_frames=3,
            camera_display_name="Test Camera",
            camera_location="Test Aisle",
            camera_default_sync_inventory=False,
        )
    )
    db.add(
        Item(
            id="ITEM001",
            name="Test Item",
            category="Test",
            aisle="A1",
            current_stock=5,
            threshold=3,
            status="normal",
        )
    )
    db.add(LabelMapping(detection_label="cola", item_id="ITEM001"))
    db.commit()
    return engine, db


def simulate_confirmation_frames(
    presence_frames: int,
    absence_frames: int,
) -> ConfirmationResult:
    engine, db = build_confirmation_session()
    camera_id = f"confirmation_{presence_frames}_{absence_frames}"

    try:
        settings_row = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
        settings_row.stock_presence_confirmation_frames = presence_frames
        settings_row.stock_absence_confirmation_frames = absence_frames
        db.commit()

        item = db.query(Item).filter(Item.id == "ITEM001").first()
        StockService.reset_runtime_state()

        presence_delay = None
        for frame_index in range(1, 12):
            StockService.process_detections(
                db=db,
                detections=[{"label": "cola", "confidence": 0.92}],
                camera_id=camera_id,
            )
            db.refresh(item)
            if item.status == "low":
                presence_delay = frame_index
                break

        if presence_delay is None:
            raise RuntimeError(
                f"Presence confirmation did not complete for {presence_frames}/{absence_frames}"
            )

        absence_delay = None
        for frame_index in range(1, 12):
            StockService.process_detections(
                db=db,
                detections=[],
                camera_id=camera_id,
            )
            db.refresh(item)
            if item.status == "out":
                absence_delay = frame_index
                break

        if absence_delay is None:
            raise RuntimeError(
                f"Absence confirmation did not complete for {presence_frames}/{absence_frames}"
            )

        note = ""
        if (presence_frames, absence_frames) == (1, 1):
            note = "Fastest reaction"
        elif (presence_frames, absence_frames) == (2, 3):
            note = "Balanced default"
        elif (presence_frames, absence_frames) == (3, 5):
            note = "Most conservative"

        return ConfirmationResult(
            presence_frames=presence_frames,
            absence_frames=absence_frames,
            presence_delay_frames=presence_delay,
            absence_delay_frames=absence_delay,
            note=note,
        )
    finally:
        db.close()
        engine.dispose()
        StockService.reset_runtime_state()


def build_parameter_report(
    threshold_rows: list[ThresholdResult],
    confirmation_rows: list[ConfirmationResult],
    run_label: str,
    model_path: Path,
    data_yaml: Path,
    imgsz: int,
    batch: int,
    workers: int,
    sample_size: int | None,
) -> str:
    best = select_recommended_threshold(threshold_rows)
    metric_best = max(
        threshold_rows,
        key=lambda row: (
            row.map5095 if row.map5095 is not None else -1.0,
            row.f1 if row.f1 is not None else -1.0,
        ),
    )
    baseline = next(
        row for row in threshold_rows if row.conf == BASELINE_CONF and row.iou == BASELINE_IOU
    )

    lines = [f"# Parameter Sensitivity Report ({run_label})", ""]
    lines.extend(
        [
            "## Run Configuration",
            f"- Model: `{model_path}`",
            f"- Data: `{data_yaml}`",
            "- Split: `val`",
            f"- Image size: `{imgsz}`",
            f"- Batch: `{batch}`",
            f"- Workers: `{workers}`",
            f"- Sample size: `{'full val split' if sample_size is None else sample_size}`",
            "",
        ]
    )
    lines.append("## Threshold Sweep")
    lines.append(
        markdown_table(
            ["conf", "iou", "precision", "recall", "map50", "map5095", "f1", "note"],
            [
                {
                    "conf": fmt(row.conf, 2),
                    "iou": fmt(row.iou, 2),
                    "precision": fmt(row.precision, 5),
                    "recall": fmt(row.recall, 5),
                    "map50": fmt(row.map50, 5),
                    "map5095": fmt(row.map5095, 5),
                    "f1": fmt(row.f1, 5),
                    "note": row.note,
                }
                for row in threshold_rows
            ],
        )
    )
    lines.extend(
        [
            "",
            f"Recommended threshold: conf={fmt(best.conf, 2)}, iou={fmt(best.iou, 2)}",
            f"Baseline threshold: conf={fmt(baseline.conf, 2)}, iou={fmt(baseline.iou, 2)}",
            (
                "Selection rationale: the default threshold is kept when its "
                f"mAP@0.5:0.95 is within {MAP5095_RECOMMENDATION_TOLERANCE:.3f} of the metric-best setting, "
                "because this avoids overfitting to a negligible validation-set difference while preserving the current deployment behavior."
                if best is baseline and metric_best is not baseline
                else "Selection rationale: the recommended threshold has the strongest mAP@0.5:0.95/F1 trade-off in this sweep."
            ),
            "",
            "## Confirmation Frame Simulation",
            markdown_table(
                [
                    "presence_frames",
                    "absence_frames",
                    "presence_delay_frames",
                    "absence_delay_frames",
                    "note",
                ],
                [
                    {
                        "presence_frames": row.presence_frames,
                        "absence_frames": row.absence_frames,
                        "presence_delay_frames": row.presence_delay_frames,
                        "absence_delay_frames": row.absence_delay_frames,
                        "note": row.note,
                    }
                    for row in confirmation_rows
                ],
            ),
            "",
            "Confirmation-frame parameters are evaluated with response delay instead of mAP because they affect state confirmation timing, not detector quality directly.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_parameter_mode(args: argparse.Namespace) -> int:
    output_csv = output_path(args.output_dir, "parameter_sensitivity", ".csv", args.tag)
    output_md = output_path(args.output_dir, "parameter_sensitivity", ".md", args.tag)
    partial_csv = output_path(args.output_dir, "parameter_sensitivity", ".partial.csv", args.tag)
    progress_json = output_path(args.output_dir, "parameter_sensitivity", ".progress.json", args.tag)

    threshold_rows = run_threshold_sweep(
        model_path=args.model,
        data_yaml=args.data,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        sample_size=args.sample_size,
        partial_csv=partial_csv,
        progress_json=progress_json,
        resume=args.resume,
    )
    confirmation_rows = [
        simulate_confirmation_frames(presence_frames, absence_frames)
        for presence_frames, absence_frames in CONFIRMATION_GRID
    ]

    csv_rows = [threshold_result_to_csv_row(row) for row in threshold_rows]
    csv_rows.extend(
        {
            "experiment_type": "confirmation",
            "conf": "",
            "iou": "",
            "presence_frames": row.presence_frames,
            "absence_frames": row.absence_frames,
            "precision": "",
            "recall": "",
            "map50": "",
            "map5095": "",
            "f1": "",
            "presence_delay_frames": row.presence_delay_frames,
            "absence_delay_frames": row.absence_delay_frames,
            "note": row.note,
        }
        for row in confirmation_rows
    )

    write_csv(
        output_csv,
        csv_rows,
        PARAMETER_CSV_FIELDS,
    )
    write_text(
        output_md,
        build_parameter_report(
            threshold_rows,
            confirmation_rows,
            args.tag or "full",
            args.model,
            args.data,
            args.imgsz,
            args.batch,
            args.workers,
            args.sample_size,
        ),
    )

    print(f"[OK] Parameter report written to {output_csv}")
    print(f"[OK] Markdown summary written to {output_md}")
    print(f"[OK] Progress trace written to {progress_json}")
    return 0


def load_frame_payloads(image_dir: Path, limit: int | None = None) -> list[str]:
    if not image_dir.exists():
        raise FileNotFoundError(f"Image directory not found: {image_dir}")

    image_paths = sorted(path for path in image_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
    if not image_paths:
        raise FileNotFoundError(f"No image files found in {image_dir}")

    if limit is not None:
        image_paths = image_paths[:limit]

    return [base64.b64encode(path.read_bytes()).decode("ascii") for path in image_paths]


def find_backend_process() -> psutil.Process:
    runtime_pid_file = PROJECT_ROOT / ".runtime" / "backend.pid"
    if runtime_pid_file.exists():
        try:
            pid = int(runtime_pid_file.read_text(encoding="utf-8").strip())
            process = psutil.Process(pid)
            if process.is_running():
                return process
        except (ValueError, psutil.Error):
            pass

    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(process.info.get("cmdline") or [])
        except (psutil.Error, TypeError):
            continue
        if "uvicorn" in cmdline and "app.main:app" in cmdline:
            return process

    raise RuntimeError("Could not find a running backend process. Start the stack with npm run dev first.")


def backend_is_healthy(base_url: str) -> bool:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/health", timeout=3.0)
    except httpx.HTTPError:
        return False
    return 200 <= response.status_code < 500


def wait_for_backend(base_url: str, timeout_seconds: int) -> None:
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        if backend_is_healthy(base_url):
            return
        time.sleep(0.75)
    raise RuntimeError(f"Backend did not become healthy within {timeout_seconds} seconds")


def start_managed_backend(base_url: str) -> ManagedBackend:
    parsed_url = urlparse(base_url)
    host = parsed_url.hostname or "127.0.0.1"
    port = parsed_url.port or (443 if parsed_url.scheme == "https" else 8000)
    log_dir = ensure_dir(PROJECT_ROOT / "validation_runs" / "experiment_tmp")
    stdout_handle = (log_dir / "stability_backend.out.log").open("ab")
    stderr_handle = (log_dir / "stability_backend.err.log").open("ab")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(BACKEND_DIR), str(PROJECT_ROOT), env.get("PYTHONPATH", "")]
    )
    env["PYTHONIOENCODING"] = "utf-8"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=str(BACKEND_DIR),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=creationflags,
    )
    return ManagedBackend(process=process, stdout_handle=stdout_handle, stderr_handle=stderr_handle)


def stop_managed_backend(managed_backend: ManagedBackend | None) -> None:
    if managed_backend is None:
        return
    process = managed_backend.process
    if process.poll() is None:
        process.terminate()
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=15)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=15)
    managed_backend.stdout_handle.close()
    managed_backend.stderr_handle.close()


def login_for_token(base_url: str, username: str, password: str) -> str:
    login_url = f"{base_url.rstrip('/')}/api/v1/auth/login"
    with httpx.Client(timeout=15.0) as client:
        response = client.post(
            login_url,
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if response.status_code != 200:
        raise RuntimeError(f"Login failed with {response.status_code}: {response.text.strip()}")

    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Login succeeded but no access token was returned")
    return token


async def stability_client(
    client_id: str,
    websocket_url: str,
    token: str,
    frame_payloads: list[str],
    duration_seconds: int,
    sync_inventory: bool,
    frame_interval_seconds: float,
    reconnect_backoff_seconds: float,
    receive_timeout_seconds: float,
) -> ClientStats:
    stats = ClientStats(client_id=client_id)
    deadline = time.perf_counter() + duration_seconds
    frame_index = 0
    websocket = None

    async def connect_ws():
        return await websockets.connect(
            f"{websocket_url}?token={token}",
            max_size=None,
            ping_interval=None,
        )

    try:
        while time.perf_counter() < deadline:
            if websocket is None:
                try:
                    websocket = await connect_ws()
                except (OSError, RuntimeError, websockets.WebSocketException):
                    stats.disconnects += 1
                    await asyncio.sleep(reconnect_backoff_seconds)
                    continue

            payload = {
                "type": "frame",
                "image": frame_payloads[frame_index % len(frame_payloads)],
                "sync_inventory": sync_inventory,
                "camera_id": client_id,
            }
            frame_index += 1

            try:
                started = time.perf_counter()
                await websocket.send(json.dumps(payload))
                stats.sent_frames += 1
                raw_message = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=receive_timeout_seconds,
                )
                stats.received_frames += 1
                stats.latencies_ms.append((time.perf_counter() - started) * 1000)

                with suppress(json.JSONDecodeError):
                    message = json.loads(raw_message)
                    if message.get("type") != "detection":
                        stats.disconnects += 1
            except (asyncio.TimeoutError, websockets.ConnectionClosed, OSError, RuntimeError):
                stats.disconnects += 1
                with suppress(Exception):
                    if websocket is not None:
                        await websocket.close()
                websocket = None
                continue

            if frame_interval_seconds > 0:
                await asyncio.sleep(frame_interval_seconds)
    finally:
        if websocket is not None:
            with suppress(Exception):
                await websocket.close()

    return stats


async def sample_runtime(
    backend_process: psutil.Process,
    duration_seconds: int,
    sample_interval_seconds: int,
) -> list[SamplePoint]:
    samples: list[SamplePoint] = []
    backend_process.cpu_percent(None)
    psutil.cpu_percent(None)
    deadline = time.perf_counter() + duration_seconds
    start = time.perf_counter()

    while time.perf_counter() < deadline:
        await asyncio.sleep(sample_interval_seconds)
        elapsed = round(time.perf_counter() - start, 2)
        try:
            backend_cpu = backend_process.cpu_percent(None)
            backend_rss = backend_process.memory_info().rss / MB
        except psutil.Error:
            backend_cpu = 0.0
            backend_rss = 0.0

        samples.append(
            SamplePoint(
                elapsed_seconds=elapsed,
                backend_cpu_pct=backend_cpu,
                backend_rss_mb=backend_rss,
                system_cpu_pct=psutil.cpu_percent(None),
                system_memory_pct=psutil.virtual_memory().percent,
            )
        )

    return samples


def summarize_stability(
    samples: list[SamplePoint],
    client_stats: list[ClientStats],
    duration_seconds: int,
) -> list[dict[str, Any]]:
    all_latencies = [latency for stats in client_stats for latency in stats.latencies_ms]
    total_sent = sum(stats.sent_frames for stats in client_stats)
    total_received = sum(stats.received_frames for stats in client_stats)
    total_disconnects = sum(stats.disconnects for stats in client_stats)

    def row(scope: str, stats: ClientStats | None = None) -> dict[str, Any]:
        latencies = stats.latencies_ms if stats else all_latencies
        backend_cpu_values = [sample.backend_cpu_pct for sample in samples]
        backend_rss_values = [sample.backend_rss_mb for sample in samples]
        system_cpu_values = [sample.system_cpu_pct for sample in samples]
        system_memory_values = [sample.system_memory_pct for sample in samples]
        return {
            "scope": scope,
            "duration_seconds": duration_seconds,
            "sent_frames": stats.sent_frames if stats else total_sent,
            "received_frames": stats.received_frames if stats else total_received,
            "disconnects": stats.disconnects if stats else total_disconnects,
            "avg_latency_ms": f"{mean_or_zero(latencies):.2f}",
            "p95_latency_ms": f"{percentile(latencies, 95):.2f}",
            "max_latency_ms": f"{max(latencies):.2f}" if latencies else "0.00",
            "backend_cpu_avg_pct": f"{mean_or_zero(backend_cpu_values):.2f}",
            "backend_cpu_peak_pct": f"{max(backend_cpu_values, default=0.0):.2f}",
            "backend_rss_avg_mb": f"{mean_or_zero(backend_rss_values):.2f}",
            "backend_rss_peak_mb": f"{max(backend_rss_values, default=0.0):.2f}",
            "system_cpu_avg_pct": f"{mean_or_zero(system_cpu_values):.2f}",
            "system_memory_avg_pct": f"{mean_or_zero(system_memory_values):.2f}",
        }

    rows = [row("aggregate")]
    rows.extend(row(stats.client_id, stats) for stats in client_stats)
    return rows


def build_stability_report(
    summary_rows: list[dict[str, Any]],
    samples: list[SamplePoint],
    run_label: str,
    duration_seconds: int,
    image_dir: Path,
    max_images: int | None,
    frame_interval_seconds: float,
) -> str:
    aggregate = summary_rows[0]
    client_rows = summary_rows[1:]
    lines = [f"# 2-Client Stability Report ({run_label})", ""]
    lines.extend(
        [
            f"- Duration: {duration_seconds} seconds",
            f"- Frame source: {image_dir}",
            f"- Frame cache: {'all available images' if max_images is None else f'first {max_images} images, looped'}",
            f"- Per-client frame interval: {frame_interval_seconds:.2f} seconds",
            "- Test mode: two concurrent websocket clients connected to /api/v1/camera/stream with sync_inventory disabled",
            "",
            "## Summary",
            markdown_table(
                [
                    "scope",
                    "sent_frames",
                    "received_frames",
                    "disconnects",
                    "avg_latency_ms",
                    "p95_latency_ms",
                    "max_latency_ms",
                    "backend_cpu_avg_pct",
                    "backend_cpu_peak_pct",
                    "backend_rss_avg_mb",
                    "backend_rss_peak_mb",
                    "system_cpu_avg_pct",
                    "system_memory_avg_pct",
                ],
                summary_rows,
            ),
            "",
            "## Samples",
            markdown_table(
                [
                    "elapsed_seconds",
                    "backend_cpu_pct",
                    "backend_rss_mb",
                    "system_cpu_pct",
                    "system_memory_pct",
                ],
                [
                    {
                        "elapsed_seconds": f"{sample.elapsed_seconds:.0f}",
                        "backend_cpu_pct": f"{sample.backend_cpu_pct:.2f}",
                        "backend_rss_mb": f"{sample.backend_rss_mb:.2f}",
                        "system_cpu_pct": f"{sample.system_cpu_pct:.2f}",
                        "system_memory_pct": f"{sample.system_memory_pct:.2f}",
                    }
                    for sample in samples
                ],
            ),
            "",
            "## Conclusion",
            f"Average latency: {aggregate['avg_latency_ms']} ms; p95 latency: {aggregate['p95_latency_ms']} ms.",
            (
                "Disconnects by client: "
                + ", ".join(f"{row['scope']}={row['disconnects']}" for row in client_rows)
                if client_rows
                else "Disconnects by client: none"
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def run_stability_mode(args: argparse.Namespace) -> int:
    output_csv = output_path(args.output_dir, "stability_2clients", ".csv", args.tag)
    output_md = output_path(args.output_dir, "stability_2clients", ".md", args.tag)

    managed_backend = None
    try:
        if backend_is_healthy(args.base_url):
            backend_process = find_backend_process()
        elif args.auto_start_backend:
            managed_backend = start_managed_backend(args.base_url)
            wait_for_backend(args.base_url, args.backend_start_timeout_seconds)
            backend_process = psutil.Process(managed_backend.process.pid)
        else:
            raise RuntimeError(
                "Backend is not healthy. Start the backend first or omit --no-auto-start-backend."
            )

        token = login_for_token(args.base_url, args.username, args.password)
        frame_payloads = load_frame_payloads(args.image_dir, args.max_images)

        duration_seconds = args.duration_minutes * 60
        sample_interval_seconds = max(1, args.sample_interval_seconds)
        websocket_url = args.base_url.rstrip("/").replace("http://", "ws://").replace(
            "https://", "wss://"
        ) + "/api/v1/camera/stream"

        async def runner():
            sample_task = asyncio.create_task(
                sample_runtime(backend_process, duration_seconds, sample_interval_seconds)
            )
            client_tasks = [
                asyncio.create_task(
                    stability_client(
                        client_id=f"stability_camera_{index + 1}",
                        websocket_url=websocket_url,
                        token=token,
                        frame_payloads=frame_payloads,
                        duration_seconds=duration_seconds,
                        sync_inventory=False,
                        frame_interval_seconds=args.frame_interval_seconds,
                        reconnect_backoff_seconds=args.reconnect_backoff_seconds,
                        receive_timeout_seconds=args.receive_timeout_seconds,
                    )
                )
                for index in range(2)
            ]

            client_stats = await asyncio.gather(*client_tasks)
            samples = await sample_task
            return client_stats, samples

        client_stats, samples = asyncio.run(runner())
        summary_rows = summarize_stability(samples, client_stats, duration_seconds)
        write_csv(
            output_csv,
            summary_rows,
            [
                "scope",
                "duration_seconds",
                "sent_frames",
                "received_frames",
                "disconnects",
                "avg_latency_ms",
                "p95_latency_ms",
                "max_latency_ms",
                "backend_cpu_avg_pct",
                "backend_cpu_peak_pct",
                "backend_rss_avg_mb",
                "backend_rss_peak_mb",
                "system_cpu_avg_pct",
                "system_memory_avg_pct",
            ],
        )
        write_text(
            output_md,
            build_stability_report(
                summary_rows=summary_rows,
                samples=samples,
                run_label=args.tag or "full",
                duration_seconds=duration_seconds,
                image_dir=args.image_dir,
                max_images=args.max_images,
                frame_interval_seconds=args.frame_interval_seconds,
            ),
        )

        print(f"[OK] Stability report written to {output_csv}")
        print(f"[OK] Markdown summary written to {output_md}")
        return 0
    finally:
        stop_managed_backend(managed_backend)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run experiment sweeps and stability tests.")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    parameter_parser = subparsers.add_parser(
        "parameters",
        help="Run detection threshold and confirmation-frame sweeps.",
    )
    parameter_parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parameter_parser.add_argument("--data", type=Path, default=DEFAULT_DATA_YAML)
    parameter_parser.add_argument("--imgsz", type=int, default=960)
    parameter_parser.add_argument("--batch", type=int, default=6)
    parameter_parser.add_argument("--workers", type=int, default=0)
    parameter_parser.add_argument("--sample-size", type=int, default=None)
    parameter_parser.add_argument("--output-dir", type=Path, default=DEFAULT_PARAM_OUTPUT_DIR)
    parameter_parser.add_argument("--resume", action="store_true", help="Reuse completed rows from the partial threshold CSV.")
    parameter_parser.add_argument("--tag", type=str, default="")
    parameter_parser.set_defaults(func=lambda args: run_parameter_mode(args))

    stability_parser = subparsers.add_parser(
        "stability",
        help="Run a two-client websocket stability test.",
    )
    stability_parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8000")
    stability_parser.add_argument("--username", type=str, default="admin")
    stability_parser.add_argument("--password", type=str, default="88888888")
    stability_parser.add_argument("--image-dir", type=Path, default=DEFAULT_STABILITY_IMAGES_DIR)
    stability_parser.add_argument("--max-images", type=int, default=None)
    stability_parser.add_argument("--duration-minutes", type=int, default=120)
    stability_parser.add_argument("--sample-interval-seconds", type=int, default=5)
    stability_parser.add_argument("--frame-interval-seconds", type=float, default=0.0)
    stability_parser.add_argument("--receive-timeout-seconds", type=float, default=30.0)
    stability_parser.add_argument("--reconnect-backoff-seconds", type=float, default=1.0)
    stability_parser.add_argument("--backend-start-timeout-seconds", type=int, default=60)
    stability_parser.add_argument("--output-dir", type=Path, default=DEFAULT_EXPERIMENT_OUTPUT_DIR)
    stability_parser.add_argument(
        "--no-auto-start-backend",
        action="store_false",
        dest="auto_start_backend",
        help="Require an already running backend instead of starting a temporary one.",
    )
    stability_parser.add_argument("--tag", type=str, default="")
    stability_parser.set_defaults(func=lambda args: run_stability_mode(args))

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    ensure_dir(args.output_dir)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
