from __future__ import annotations

from typing import Any, Dict

import torch
from torch import nn
from torchvision.models import MobileNet_V3_Large_Weights, mobilenet_v3_large


class CountMobileNetV3(nn.Module):
    """MobileNetV3-Large count regressor with a class-id embedding branch."""

    def __init__(
        self,
        num_classes: int = 93,
        embedding_dim: int = 32,
        hidden_dim: int = 256,
        dropout: float = 0.2,
        pretrained: bool = True,
    ) -> None:
        super().__init__()
        weights = MobileNet_V3_Large_Weights.IMAGENET1K_V2 if pretrained else None
        backbone = mobilenet_v3_large(weights=weights)
        in_features = backbone.classifier[0].in_features
        backbone.classifier = nn.Identity()

        self.backbone = backbone
        self.class_embedding = nn.Embedding(num_classes, embedding_dim)
        self.regressor = nn.Sequential(
            nn.Linear(in_features + embedding_dim, hidden_dim),
            nn.Hardswish(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
        )
        self.num_classes = num_classes
        self.embedding_dim = embedding_dim
        self.hidden_dim = hidden_dim
        self.dropout = dropout

    def forward(self, images: torch.Tensor, class_ids: torch.Tensor) -> torch.Tensor:
        class_ids = class_ids.long().clamp(0, self.num_classes - 1)
        features = self.backbone(images)
        class_features = self.class_embedding(class_ids)
        joined = torch.cat([features, class_features], dim=1)
        return self.regressor(joined).squeeze(1)

    def config(self) -> Dict[str, Any]:
        return {
            "num_classes": self.num_classes,
            "embedding_dim": self.embedding_dim,
            "hidden_dim": self.hidden_dim,
            "dropout": self.dropout,
        }


def build_count_model(
    num_classes: int = 93,
    embedding_dim: int = 32,
    hidden_dim: int = 256,
    dropout: float = 0.2,
    pretrained: bool = True,
) -> CountMobileNetV3:
    return CountMobileNetV3(
        num_classes=num_classes,
        embedding_dim=embedding_dim,
        hidden_dim=hidden_dim,
        dropout=dropout,
        pretrained=pretrained,
    )


def model_from_checkpoint(checkpoint: Dict[str, Any], pretrained: bool = False) -> CountMobileNetV3:
    config = checkpoint.get("model_config", {})
    model = build_count_model(
        num_classes=int(config.get("num_classes", checkpoint.get("num_classes", 93))),
        embedding_dim=int(config.get("embedding_dim", 32)),
        hidden_dim=int(config.get("hidden_dim", 256)),
        dropout=float(config.get("dropout", 0.2)),
        pretrained=pretrained,
    )
    state_dict = checkpoint.get("model", checkpoint.get("state_dict", checkpoint))
    if any(str(key).startswith("module.") for key in state_dict.keys()):
        state_dict = {str(key).removeprefix("module."): value for key, value in state_dict.items()}
    model.load_state_dict(state_dict, strict=True)
    return model
