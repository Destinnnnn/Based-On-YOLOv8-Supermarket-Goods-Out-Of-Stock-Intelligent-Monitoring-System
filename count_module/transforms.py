from __future__ import annotations

from pathlib import Path
from typing import Sequence, Tuple, Union

import numpy as np
import torch
from PIL import Image


ImageInput = Union[str, Path, Image.Image, np.ndarray]

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def load_image(image: ImageInput, array_color: str = "RGB") -> Image.Image:
    """Load a supported image input as an RGB PIL image."""
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    if isinstance(image, (str, Path)):
        return Image.open(image).convert("RGB")
    if isinstance(image, np.ndarray):
        array = image
        if array.ndim == 2:
            return Image.fromarray(array).convert("RGB")
        if array.ndim != 3:
            raise ValueError(f"Expected image ndarray with 2 or 3 dims, got shape {array.shape}")
        if array.shape[2] == 4:
            array = array[:, :, :3]
        if array.shape[2] != 3:
            raise ValueError(f"Expected image ndarray with 3 channels, got shape {array.shape}")
        if array.dtype != np.uint8:
            array = np.clip(array, 0, 255).astype(np.uint8)
        color = array_color.upper()
        if color == "BGR":
            array = array[:, :, ::-1]
        elif color != "RGB":
            raise ValueError("array_color must be 'RGB' or 'BGR'")
        array = np.ascontiguousarray(array)
        return Image.fromarray(array).convert("RGB")
    raise TypeError(f"Unsupported image type: {type(image)!r}")


def expand_xyxy(
    xyxy: Sequence[float],
    image_size: Tuple[int, int],
    pad_ratio: float = 0.08,
) -> Tuple[int, int, int, int]:
    """Pad and clip an xyxy box to image bounds."""
    if len(xyxy) != 4:
        raise ValueError(f"xyxy must have 4 values, got {len(xyxy)}")

    width, height = image_size
    x1, y1, x2, y2 = [float(v) for v in xyxy]
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1

    box_w = max(x2 - x1, 1.0)
    box_h = max(y2 - y1, 1.0)
    pad_x = box_w * pad_ratio
    pad_y = box_h * pad_ratio

    left = int(np.floor(max(0.0, x1 - pad_x)))
    top = int(np.floor(max(0.0, y1 - pad_y)))
    right = int(np.ceil(min(float(width), x2 + pad_x)))
    bottom = int(np.ceil(min(float(height), y2 + pad_y)))

    if right <= left:
        right = min(width, left + 1)
    if bottom <= top:
        bottom = min(height, top + 1)
    return left, top, right, bottom


def crop_box(image: Image.Image, xyxy: Sequence[float], pad_ratio: float = 0.08) -> Image.Image:
    box = expand_xyxy(xyxy, image.size, pad_ratio=pad_ratio)
    return image.crop(box)


def image_to_tensor(image: Image.Image, image_size: int = 224) -> torch.Tensor:
    """Resize and normalize a PIL image to CHW float tensor."""
    if image_size <= 0:
        raise ValueError("image_size must be positive")
    resample = Image.Resampling.BILINEAR if hasattr(Image, "Resampling") else Image.BILINEAR
    resized = image.resize((image_size, image_size), resample)
    array = np.asarray(resized, dtype=np.float32) / 255.0
    if array.ndim == 2:
        array = np.stack([array, array, array], axis=-1)
    tensor = torch.from_numpy(array).permute(2, 0, 1)
    mean = torch.tensor(IMAGENET_MEAN, dtype=torch.float32).view(3, 1, 1)
    std = torch.tensor(IMAGENET_STD, dtype=torch.float32).view(3, 1, 1)
    return (tensor - mean) / std


def crop_to_tensor(
    image: Image.Image,
    xyxy: Sequence[float],
    image_size: int = 224,
    pad_ratio: float = 0.08,
) -> torch.Tensor:
    return image_to_tensor(crop_box(image, xyxy, pad_ratio=pad_ratio), image_size=image_size)
