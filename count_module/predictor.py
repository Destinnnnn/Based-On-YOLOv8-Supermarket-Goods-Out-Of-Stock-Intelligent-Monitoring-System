from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import torch

from .model import model_from_checkpoint
from .transforms import ImageInput, crop_to_tensor, load_image


class CountPredictor:
    """Local crop-count inference entry point.

    The detector remains outside this module. Pass the original image and YOLO
    detections in xyxy pixel coordinates; this class appends a rounded `count`.
    """

    def __init__(
        self,
        weights: str | Path,
        device: str | torch.device | None = None,
        image_size: int | None = None,
        pad_ratio: float | None = None,
        min_count: int | None = None,
        max_count: int | None = None,
        array_color: str = "RGB",
    ) -> None:
        self.weights = Path(weights)
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))

        checkpoint = torch.load(self.weights, map_location="cpu")
        self.image_size = int(image_size if image_size is not None else checkpoint.get("image_size", 224))
        self.pad_ratio = float(pad_ratio if pad_ratio is not None else checkpoint.get("pad_ratio", 0.08))
        self.min_count = int(min_count if min_count is not None else checkpoint.get("min_count", 1))
        self.max_count = int(max_count if max_count is not None else checkpoint.get("max_count", 56))
        self.array_color = array_color
        self.model = model_from_checkpoint(checkpoint, pretrained=False)
        self.model.to(self.device)
        self.model.eval()

    @torch.inference_mode()
    def predict(
        self,
        image: ImageInput,
        detections: Sequence[Mapping[str, Any]],
        batch_size: int = 64,
    ) -> List[Dict[str, Any]]:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        pil_image = load_image(image, array_color=self.array_color)
        outputs = [deepcopy(dict(det)) for det in detections]
        if not outputs:
            return outputs

        for start in range(0, len(outputs), batch_size):
            batch = outputs[start : start + batch_size]
            tensors = []
            class_ids = []
            for det in batch:
                if "xyxy" not in det:
                    raise KeyError("Each detection must contain an 'xyxy' field")
                if "class_id" not in det:
                    raise KeyError("Each detection must contain a 'class_id' field")
                tensors.append(
                    crop_to_tensor(
                        pil_image,
                        det["xyxy"],
                        image_size=self.image_size,
                        pad_ratio=self.pad_ratio,
                    )
                )
                class_ids.append(int(det["class_id"]))

            images_tensor = torch.stack(tensors, dim=0).to(self.device, non_blocking=True)
            class_tensor = torch.tensor(class_ids, dtype=torch.long, device=self.device)
            raw_counts = self.model(images_tensor, class_tensor)
            counts = raw_counts.round().clamp(self.min_count, self.max_count).to(torch.int64)
            for det, count in zip(batch, counts.cpu().tolist()):
                det["count"] = int(count)
        return outputs
