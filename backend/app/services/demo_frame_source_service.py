from __future__ import annotations

import base64
import random
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.core.config import settings


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class DemoFrame:
    image_bytes: bytes
    image_data_url: str
    image_name: str
    frame_index: int
    kind: str
    cache_key: str | None


@dataclass(frozen=True)
class DemoFrameStep:
    kind: str
    image_path: Path | None
    cache_key: str | None


class DemoFrameSession:
    def __init__(
        self,
        *,
        steps: list[DemoFrameStep],
        empty_frame_bytes: bytes,
        image_count: int,
    ) -> None:
        if not steps:
            raise ValueError("Demo frame session requires at least one frame")

        self._steps = steps
        self._empty_frame_bytes = empty_frame_bytes
        self.image_count = image_count
        self.frame_count = len(steps)
        self._cursor = 0

    def next_frame(self) -> DemoFrame:
        frame_index = self._cursor
        step = self._steps[frame_index % len(self._steps)]
        self._cursor += 1

        if step.kind == "empty":
            image_bytes = self._empty_frame_bytes
            image_name = "__empty_frame__.jpg"
        elif step.image_path is not None:
            image_bytes = step.image_path.read_bytes()
            image_name = step.image_path.name
        else:
            raise ValueError("Invalid demo frame step")

        return DemoFrame(
            image_bytes=image_bytes,
            image_data_url=_to_jpeg_data_url(image_bytes),
            image_name=image_name,
            frame_index=frame_index,
            kind=step.kind,
            cache_key=step.cache_key,
        )


class DemoFrameSourceService:
    SOURCE_DIRS = {
        "test": (
            Path("datasets") / "test" / "images",
        ),
    }

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or settings.PROJECT_ROOT).resolve()

    def create_session(
        self,
        *,
        source: str = "test",
        max_images: int = 20,
        seed: int = 20260519,
        repeat_min: int = 5,
        repeat_max: int = 10,
        empty_interval: int = 5,
        empty_frames: int = 3,
    ) -> DemoFrameSession:
        if source not in self.SOURCE_DIRS:
            raise ValueError(f"Unsupported demo frame source: {source}")
        if max_images < 1:
            raise ValueError("max_images must be at least 1")
        if repeat_min < 1 or repeat_max < repeat_min:
            raise ValueError("repeat range must be positive and ordered")
        if empty_interval < 0 or empty_frames < 0:
            raise ValueError("empty frame settings must be non-negative")

        image_dir = self._resolve_source_dir(source)
        image_paths = sorted(
            path
            for path in image_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        if not image_paths:
            raise FileNotFoundError(f"No demo images found in {image_dir}")

        rng = random.Random(seed)
        shuffled_paths = image_paths[:]
        rng.shuffle(shuffled_paths)
        selected_paths = shuffled_paths[: min(max_images, len(shuffled_paths))]

        steps: list[DemoFrameStep] = []
        for image_number, image_path in enumerate(selected_paths, start=1):
            repeat_count = rng.randint(repeat_min, repeat_max)
            cache_key = str(image_path.relative_to(self.project_root).as_posix())
            steps.extend(
                DemoFrameStep(kind="image", image_path=image_path, cache_key=cache_key)
                for _ in range(repeat_count)
            )

            if empty_interval and image_number % empty_interval == 0:
                steps.extend(
                    DemoFrameStep(kind="empty", image_path=None, cache_key=None)
                    for _ in range(empty_frames)
                )

        return DemoFrameSession(
            steps=steps,
            empty_frame_bytes=self._build_empty_frame_bytes(selected_paths[0]),
            image_count=len(selected_paths),
        )

    def _resolve_source_dir(self, source: str) -> Path:
        for relative_path in self.SOURCE_DIRS[source]:
            candidate = (self.project_root / relative_path).resolve()
            if candidate.exists() and candidate.is_dir():
                self._ensure_within_project(candidate)
                return candidate

        expected = ", ".join(str(path) for path in self.SOURCE_DIRS[source])
        raise FileNotFoundError(f"No available demo frame source directory found: {expected}")

    def _ensure_within_project(self, path: Path) -> None:
        try:
            path.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError("Demo frame source must stay within the project directory") from exc

    @staticmethod
    def _build_empty_frame_bytes(reference_image_path: Path) -> bytes:
        reference = cv2.imread(str(reference_image_path), cv2.IMREAD_COLOR)
        if reference is None:
            height, width = 720, 1280
        else:
            height, width = reference.shape[:2]

        empty_frame = np.zeros((height, width, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", empty_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            raise RuntimeError("Failed to encode empty demo frame")
        return encoded.tobytes()


def _to_jpeg_data_url(image_bytes: bytes) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


demo_frame_source_service = DemoFrameSourceService()
