"""
YOLOv8 model training script for the supermarket product dataset.

Features:
- Full training on the converted dataset
- Quick test training for debugging
- Validation of a trained model
- Stable path handling after scripts/ relocation
- Safer run directory handling for repeated training
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import torch
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
PRETRAINED_MODEL_PATH = PROJECT_ROOT / "yolov8n.pt"

FULL_DATA_YAML = PROJECT_ROOT / "datasets" / "data.yaml"
QUICK_DATA_YAML = PROJECT_ROOT / "datasets" / "locount_quick" / "data.yaml"


def prepare_ultralytics_runtime() -> None:
    """
    Disable optional font checks that pull in matplotlib.

    The current local environment has a NumPy/matplotlib binary mismatch, but
    training itself can still run if we skip font validation and plot generation.
    """
    import ultralytics.data.utils as data_utils
    import ultralytics.data.dataset as dataset_module
    import ultralytics.utils.checks as checks

    def _noop(*args, **kwargs):
        return None

    checks.check_font = _noop
    data_utils.check_font = _noop

    if os.name == "nt":
        patch_windows_dataset_cache(dataset_module)


def patch_windows_dataset_cache(dataset_module) -> None:
    """
    Patch Ultralytics label caching on Windows.

    Some local Windows Python environments can fail when Ultralytics builds
    label caches with ThreadPool/multiprocessing primitives, raising
    PermissionError: [WinError 5]. A sequential cache build is slower but much
    more stable for local training and validation.
    """
    yolo_dataset_cls = dataset_module.YOLODataset
    if getattr(yolo_dataset_cls, "_codex_windows_cache_patch", False):
        return

    def cache_labels_sequential(self, path: Path = Path("./labels.cache")) -> dict:
        x = {"labels": []}
        nm, nf, ne, nc, msgs = 0, 0, 0, 0, []
        desc = f"{self.prefix}Scanning {path.parent / path.stem}..."
        total = len(self.im_files)
        nkpt, ndim = self.data.get("kpt_shape", (0, 0))
        if self.use_keypoints and (nkpt <= 0 or ndim not in {2, 3}):
            raise ValueError(
                "'kpt_shape' in data.yaml missing or incorrect. Should be a list with [number of "
                "keypoints, number of dims (2 for x,y or 3 for x,y,visible)], i.e. 'kpt_shape: [17, 3]'"
            )

        iterable = zip(
            self.im_files,
            self.label_files,
            [self.prefix] * total,
            [self.use_keypoints] * total,
            [len(self.data["names"])] * total,
            [nkpt] * total,
            [ndim] * total,
            [self.single_cls] * total,
        )

        pbar = dataset_module.TQDM(iterable, desc=desc, total=total)
        for item in pbar:
            im_file, lb, shape, segments, keypoint, nm_f, nf_f, ne_f, nc_f, msg = dataset_module.verify_image_label(item)
            nm += nm_f
            nf += nf_f
            ne += ne_f
            nc += nc_f
            if im_file:
                x["labels"].append(
                    {
                        "im_file": im_file,
                        "shape": shape,
                        "cls": lb[:, 0:1],
                        "bboxes": lb[:, 1:],
                        "segments": segments,
                        "keypoints": keypoint,
                        "normalized": True,
                        "bbox_format": "xywh",
                    }
                )
            if msg:
                msgs.append(msg)
            pbar.desc = f"{desc} {nf} images, {nm + ne} backgrounds, {nc} corrupt"
        pbar.close()

        if msgs:
            dataset_module.LOGGER.info("\n".join(msgs))
        if nf == 0:
            dataset_module.LOGGER.warning(f"{self.prefix}No labels found in {path}. {dataset_module.HELP_URL}")
        x["hash"] = dataset_module.get_hash(self.label_files + self.im_files)
        x["results"] = nf, nm, ne, nc, len(self.im_files)
        x["msgs"] = msgs
        try:
            dataset_module.save_dataset_cache_file(self.prefix, path, x, dataset_module.DATASET_CACHE_VERSION)
        except PermissionError as exc:
            dataset_module.LOGGER.warning(f"{self.prefix}Could not write label cache {path}: {exc}")
        return x

    yolo_dataset_cls.cache_labels = cache_labels_sequential
    yolo_dataset_cls._codex_windows_cache_patch = True


def resolve_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def resolve_workers(user_workers: int | None = None) -> int:
    if user_workers is not None:
        return user_workers

    # Windows dataloader workers are more likely to hang or behave unstably
    # on local training setups, so default to a conservative value.
    if os.name == "nt":
        return 0

    return min(8, os.cpu_count() or 1)


def require_path(path: Path, label: str) -> bool:
    if path.exists():
        return True

    print(f"Error: {label} not found: {path}")
    return False


def require_dataset(data_yaml: Path) -> bool:
    if data_yaml.exists():
        return True

    print(f"Error: data.yaml not found at {data_yaml}")
    print("Please run python scripts/prepare_locount_tvt_dataset.py first")
    return False


def load_model(model_path: Path) -> YOLO | None:
    if not require_path(model_path, "model file"):
        return None

    print(f"\nLoading model weights: {model_path}")
    return YOLO(str(model_path))


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def print_runtime_info(device: str, workers: int) -> None:
    print(f"\nUsing device: {device}")
    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"Workers: {workers}")


def resolve_save_dir(results, default_dir: Path) -> Path:
    save_dir = getattr(results, "save_dir", None)
    if save_dir:
        return Path(save_dir)

    trainer = getattr(results, "trainer", None)
    trainer_save_dir = getattr(trainer, "save_dir", None)
    if trainer_save_dir:
        return Path(trainer_save_dir)

    return default_dir


def copy_best_model(best_model: Path, target_name: str = "best.pt") -> Path | None:
    if not best_model.exists():
        print(f"[WARN] Best model not found: {best_model}")
        return None

    target = MODELS_DIR / target_name
    shutil.copy2(best_model, target)
    print(f"Best model copied to: {target}")
    return target


def print_metrics(metrics_dict: dict) -> None:
    print("\nMetrics:")
    print(f"  mAP@0.5: {metrics_dict.get('metrics/mAP50(B)', 'N/A')}")
    print(f"  mAP@0.5:0.95: {metrics_dict.get('metrics/mAP50-95(B)', 'N/A')}")
    print(f"  Precision: {metrics_dict.get('metrics/precision(B)', 'N/A')}")
    print(f"  Recall: {metrics_dict.get('metrics/recall(B)', 'N/A')}")


def train_yolov8(args: argparse.Namespace):
    """Train YOLOv8 model on the full custom dataset."""
    prepare_ultralytics_runtime()
    MODELS_DIR.mkdir(exist_ok=True)

    data_yaml = Path(args.data) if args.data else FULL_DATA_YAML
    model_path = Path(args.model) if args.model else PRETRAINED_MODEL_PATH
    workers = resolve_workers(args.workers)
    device = resolve_device()

    if not require_dataset(data_yaml):
        return None

    model = load_model(model_path)
    if model is None:
        return None

    print_runtime_info(device, workers)
    print_header("YOLOv8 Model Training")

    print("\nTraining Configuration:")
    print(f"  Dataset: {data_yaml}")
    print(f"  Epochs: {args.epochs}")
    print(f"  Batch size: {args.batch}")
    print(f"  Image size: {args.imgsz}")
    print(f"  Run name: {args.name}")
    print(f"  Device: {device}")

    print("\nStarting training...")
    print("This may take several hours depending on your hardware.")
    print("-" * 60)

    train_kwargs = dict(
        data=str(data_yaml),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=device,
        workers=workers,
        project=str(MODELS_DIR),
        name=args.name,
        patience=args.patience,
        save=True,
        plots=False,
        verbose=True,
    )
    # Optional augmentation & loss parameters
    optional_params = {
        "mixup": args.mixup,
        "cls": args.cls,
        "cos_lr": args.cos_lr if args.cos_lr else None,
        "copy_paste": args.copy_paste,
        "mosaic": args.mosaic,
        "close_mosaic": args.close_mosaic,
        "erasing": args.erasing,
        "degrees": args.degrees,
        "scale": args.scale,
        "lr0": args.lr0,
        "lrf": args.lrf,
    }
    for k, v in optional_params.items():
        if v is not None:
            train_kwargs[k] = v

    results = model.train(**train_kwargs)

    save_dir = resolve_save_dir(results, MODELS_DIR / args.name)
    best_model = save_dir / "weights" / "best.pt"
    last_model = save_dir / "weights" / "last.pt"

    print_header("Training completed!")
    print(f"\nRun directory: {save_dir}")
    print(f"Best model saved to: {best_model}")
    print(f"Last model saved to: {last_model}")

    copy_best_model(best_model)
    print_metrics(results.results_dict)
    return results


def evaluate_model(
    model_path: Path,
    data_yaml: Path,
    workers: int | None = None,
    imgsz: int = 640,
    batch: int = 8,
    split: str = "val",
):
    prepare_ultralytics_runtime()

    if not require_dataset(data_yaml):
        return None
    if not require_path(model_path, "model file"):
        return None

    actual_workers = resolve_workers(workers)

    print_header("YOLOv8 Validation")
    print(f"Model  : {model_path}")
    print(f"Dataset: {data_yaml}")
    print(f"Split  : {split}")
    print(f"Workers: {actual_workers}")

    model = YOLO(str(model_path))
    metrics = model.val(
        data=str(data_yaml),
        split=split,
        imgsz=imgsz,
        batch=batch,
        device=resolve_device(),
        workers=actual_workers,
        plots=False,
        verbose=True,
    )

    print_metrics(metrics.results_dict)
    return metrics


def quick_test_train(args: argparse.Namespace):
    """Quick training test with a smaller dataset configuration."""
    prepare_ultralytics_runtime()
    MODELS_DIR.mkdir(exist_ok=True)

    data_yaml = Path(args.data) if args.data else (QUICK_DATA_YAML if QUICK_DATA_YAML.exists() else FULL_DATA_YAML)
    eval_yaml = Path(args.eval_data) if args.eval_data else data_yaml
    model_path = Path(args.model) if args.model else PRETRAINED_MODEL_PATH
    workers = resolve_workers(args.workers)

    if not require_dataset(data_yaml):
        return None

    model = load_model(model_path)
    if model is None:
        return None

    print_runtime_info(resolve_device(), workers)
    print_header("YOLOv8 Quick Test Training")
    print(f"Train dataset: {data_yaml}")
    print(f"Eval dataset : {eval_yaml}")

    train_kwargs = dict(
        data=str(data_yaml),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=resolve_device(),
        workers=workers,
        project=str(MODELS_DIR),
        name=args.name,
        save=True,
        plots=False,
        verbose=True,
    )
    if args.mixup is not None:
        train_kwargs["mixup"] = args.mixup

    results = model.train(**train_kwargs)

    save_dir = resolve_save_dir(results, MODELS_DIR / args.name)
    best_model = save_dir / "weights" / "best.pt"
    eval_metrics = evaluate_model(best_model, eval_yaml, workers=workers, split=args.val_split)

    summary = {
        "train_results": results.results_dict,
        "eval_results": eval_metrics.results_dict if eval_metrics else None,
        "train_dataset": str(data_yaml),
        "eval_dataset": str(eval_yaml),
        "best_model": str(best_model),
        "save_dir": str(save_dir),
    }
    summary_path = save_dir / "quick_eval_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n[OK] Quick test completed!")
    print(f"[OK] Run directory: {save_dir}")
    print(f"[OK] Summary saved to: {summary_path}")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train or validate the YOLOv8 supermarket model.")
    parser.add_argument("--test", action="store_true", help="Run quick test training instead of full training.")
    parser.add_argument("--data", type=str, help="Path to training data.yaml.")
    parser.add_argument("--eval-data", type=str, help="Path to evaluation data.yaml for quick test.")
    parser.add_argument("--model", type=str, help="Path to pretrained model weights.")
    parser.add_argument("--epochs", type=int, help="Training epochs. Full training defaults to 100, quick test defaults to 5.")
    parser.add_argument("--batch", type=int, help="Batch size. Full training defaults to 16, quick test defaults to 8.")
    parser.add_argument("--imgsz", type=int, default=640, help="Training image size. Default: 640.")
    parser.add_argument("--name", type=str, help="Training run name.")
    parser.add_argument("--workers", type=int, help="Dataloader workers. Windows defaults to 0 for stability.")
    parser.add_argument("--patience", type=int, default=10, help="Early stopping patience for full training. Default: 10.")
    parser.add_argument("--mixup", type=float, help="MixUp augmentation ratio. Example: 0.05.")
    parser.add_argument("--val-model", type=str, help="Validate an existing model and exit.")
    parser.add_argument("--val-split", choices=["val", "test"], default="val", help="Dataset split for model validation. Default: val.")
    # Augmentation & loss tuning parameters
    parser.add_argument("--cls", type=float, help="Classification loss weight. Default YOLO: 0.5. Increase to boost Recall.")
    parser.add_argument("--cos-lr", action="store_true", help="Use cosine learning rate scheduler.")
    parser.add_argument("--copy-paste", type=float, help="Copy-paste augmentation ratio. Default: 0.0.")
    parser.add_argument("--mosaic", type=float, help="Mosaic augmentation ratio. Default: 1.0.")
    parser.add_argument("--close-mosaic", type=int, help="Disable mosaic for last N epochs. Default: 10.")
    parser.add_argument("--erasing", type=float, help="Random erasing augmentation ratio. Default: 0.4.")
    parser.add_argument("--degrees", type=float, help="Random rotation degrees. Default: 0.0.")
    parser.add_argument("--scale", type=float, help="Image scale augmentation range. Default: 0.5.")
    parser.add_argument("--lr0", type=float, help="Initial learning rate. Default: 0.01.")
    parser.add_argument("--lrf", type=float, help="Final learning rate factor. Default: 0.01.")
    parser.add_argument("--val-imgsz", type=int, default=640, help="Validation image size. Default: 640.")
    parser.add_argument("--val-batch", type=int, default=8, help="Validation batch size. Default: 8.")
    return parser


def apply_mode_defaults(args: argparse.Namespace) -> argparse.Namespace:
    if args.test:
        if args.epochs is None:
            args.epochs = 5
        if args.batch is None:
            args.batch = 8
        if args.name is None:
            args.name = "locount_quick_5ep"
    else:
        if args.epochs is None:
            args.epochs = 100
        if args.batch is None:
            args.batch = 16
        if args.name is None:
            args.name = "yolov8_supermarket"

    return args


def main() -> int:
    parser = build_parser()
    args = apply_mode_defaults(parser.parse_args())

    if args.val_model:
        data_yaml = Path(args.data) if args.data else FULL_DATA_YAML
        metrics = evaluate_model(
            Path(args.val_model),
            data_yaml,
            workers=args.workers,
            imgsz=args.val_imgsz,
            batch=args.val_batch,
            split=args.val_split,
        )
        return 0 if metrics is not None else 1

    if args.test:
        print("Running quick test training...")
        quick_test_train(args)
        return 0

    print("Starting full training...")
    print("Tip: Use --test for a quick 5-epoch validation run before full training.")
    train_yolov8(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
