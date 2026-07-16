"""
Stock Management Service
Handles stock status determination and database updates
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Dict, List, Set

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.detection import Detection
from app.models.detection_box import DetectionBox
from app.models.item import Item
from app.models.label_mapping import LabelMapping
from app.models.stock_history import StockHistory
from app.services.settings_service import settings_service

logger = logging.getLogger(__name__)


@dataclass
class PendingStatusUpdate:
    status: str
    frames_seen: int
    current_stock: int
    confidence: float
    source: str
    boxes: List[Dict] = field(default_factory=list)


@dataclass
class CameraRuntimeState:
    observed_item_ids: Set[str] = field(default_factory=set)
    pending_updates: Dict[str, PendingStatusUpdate] = field(default_factory=dict)


class StockService:
    _camera_states: ClassVar[Dict[str, CameraRuntimeState]] = {}

    @staticmethod
    def determine_stock_status(detected_count: int, threshold: int) -> str:
        """
        Determine stock status based on detected count and threshold

        Args:
            detected_count: Number of items detected
            threshold: Minimum acceptable stock level

        Returns:
            'out' (out of stock), 'low' (low stock), or 'normal'
        """
        if detected_count == 0:
            return "out"
        if detected_count < threshold:
            return "low"
        return "normal"

    @classmethod
    def reset_runtime_state(cls):
        cls._camera_states = {}

    @classmethod
    def _get_camera_state(cls, camera_id: str) -> CameraRuntimeState:
        state = cls._camera_states.get(camera_id)
        if state is None:
            state = CameraRuntimeState()
            cls._camera_states[camera_id] = state
        return state

    @staticmethod
    def _build_item_lookup(items: List[Item]) -> Dict[str, Item]:
        return {item.id: item for item in items}

    @classmethod
    def _required_frames(cls, source: str, runtime_settings) -> int:
        if source == "absence":
            return runtime_settings.stock_absence_confirmation_frames
        return runtime_settings.stock_presence_confirmation_frames

    @classmethod
    def _apply_update(
        cls,
        *,
        db: Session,
        item: Item,
        update: PendingStatusUpdate,
        camera_id: str,
        updated_items: List[Item],
        status_changes: List[Dict],
    ):
        old_status = item.status
        item.current_stock = update.current_stock
        item.status = update.status
        item.last_updated = datetime.utcnow()

        detection_record = Detection(
            item_id=item.id,
            detected_count=update.current_stock,
            confidence=update.confidence,
            camera_id=camera_id,
        )
        db.add(detection_record)
        db.flush()

        for box in update.boxes:
            db.add(
                DetectionBox(
                    detection_id=detection_record.id,
                    item_id=item.id,
                    camera_id=camera_id,
                    label=str(box.get("label", "")),
                    class_id=box.get("class_id"),
                    x=float(box.get("x", 0.0)),
                    y=float(box.get("y", 0.0)),
                    w=float(box.get("w", 0.0)),
                    h=float(box.get("h", 0.0)),
                    confidence=box.get("confidence"),
                    predicted_count=cls._resolve_predicted_count(box),
                    count_model_version=box.get("count_model_version"),
                )
            )

        db.add(
            StockHistory(
                item_id=item.id,
                stock_level=update.current_stock,
            )
        )

        updated_items.append(item)

        if old_status != update.status:
            status_changes.append(
                {
                    "item_id": item.id,
                    "item_name": item.name,
                    "old_status": old_status,
                    "new_status": update.status,
                    "current_stock": update.current_stock,
                    "threshold": item.threshold,
                }
            )
            logger.info("Status change: %s %s -> %s", item.name, old_status, update.status)

    @staticmethod
    def _resolve_predicted_count(det: Dict) -> int:
        try:
            count = int(det.get("predicted_count", 1))
        except (TypeError, ValueError):
            return 1
        return max(1, count)

    @classmethod
    def process_detections(cls, db: Session, detections: List[Dict], camera_id: str = "default"):
        """
        Process detection results and update stock status.

        The service keeps per-camera runtime state so status transitions only
        happen after consecutive confirming frames. Out-of-stock inference is
        intentionally limited to consecutive empty frames for items that this
        camera has already seen before.
        """
        state = cls._get_camera_state(camera_id)
        runtime_settings = settings_service.get_runtime_settings(db)

        items = db.query(Item).all()
        item_by_id = cls._build_item_lookup(items)
        item_by_name = {item.name: item for item in items}
        state.observed_item_ids.intersection_update(item_by_id.keys())

        label_mappings = db.query(LabelMapping).all()
        item_by_label = {
            mapping.detection_label: item_by_id.get(mapping.item_id)
            for mapping in label_mappings
            if mapping.item_id in item_by_id
        }

        detection_counts: Dict[str, int] = {}
        confidence_totals: Dict[str, float] = {}
        box_counts: Dict[str, int] = {}
        matched_boxes: Dict[str, List[Dict]] = {}
        matched_detection_labels: set[str] = set()
        unmatched_detection_labels: set[str] = set()

        for det in detections:
            label = det["label"]
            item = item_by_label.get(label) or item_by_name.get(label)

            if not item:
                unmatched_detection_labels.add(label)
                continue

            predicted_count = cls._resolve_predicted_count(det)
            detection_counts[item.id] = detection_counts.get(item.id, 0) + predicted_count
            confidence_totals[item.id] = confidence_totals.get(item.id, 0.0) + det["confidence"]
            box_counts[item.id] = box_counts.get(item.id, 0) + 1
            matched_boxes.setdefault(item.id, []).append(det)
            matched_detection_labels.add(label)
            state.observed_item_ids.add(item.id)

        logger.info("Detection counts by item for %s: %s", camera_id, detection_counts)

        proposed_updates: Dict[str, PendingStatusUpdate] = {}

        for item_id, count in detection_counts.items():
            item = item_by_id.get(item_id)
            if not item:
                continue

            proposed_updates[item_id] = PendingStatusUpdate(
                status=cls.determine_stock_status(count, item.threshold),
                frames_seen=0,
                current_stock=count,
                confidence=confidence_totals[item_id] / box_counts[item_id] if box_counts.get(item_id) else 0.0,
                source="presence",
                boxes=matched_boxes.get(item_id, []),
            )

        if not detections:
            for item_id in state.observed_item_ids:
                if item_id not in item_by_id:
                    continue
                proposed_updates[item_id] = PendingStatusUpdate(
                    status="out",
                    frames_seen=0,
                    current_stock=0,
                    confidence=0.0,
                    source="absence",
                    boxes=[],
                )

        updated_items: List[Item] = []
        status_changes: List[Dict] = []

        for item_id, update in proposed_updates.items():
            item = item_by_id.get(item_id)
            if not item:
                continue

            if item.status == update.status:
                state.pending_updates.pop(item_id, None)
                if item.current_stock != update.current_stock:
                    cls._apply_update(
                        db=db,
                        item=item,
                        update=update,
                        camera_id=camera_id,
                        updated_items=updated_items,
                        status_changes=status_changes,
                    )
                continue

            pending = state.pending_updates.get(item_id)
            if (
                pending
                and pending.status == update.status
                and pending.source == update.source
            ):
                frames_seen = pending.frames_seen + 1
            else:
                frames_seen = 1

            next_pending = PendingStatusUpdate(
                status=update.status,
                frames_seen=frames_seen,
                current_stock=update.current_stock,
                confidence=update.confidence,
                source=update.source,
                boxes=update.boxes,
            )

            if frames_seen >= cls._required_frames(update.source, runtime_settings):
                state.pending_updates.pop(item_id, None)
                cls._apply_update(
                    db=db,
                    item=item,
                    update=next_pending,
                    camera_id=camera_id,
                    updated_items=updated_items,
                    status_changes=status_changes,
                )
            else:
                state.pending_updates[item_id] = next_pending

        for item_id in list(state.pending_updates):
            if item_id not in proposed_updates:
                state.pending_updates.pop(item_id, None)

        db.commit()

        pending_status_updates = [
            {
                "item_id": item_id,
                "item_name": item_by_id[item_id].name,
                "status": pending.status,
                "frames_seen": pending.frames_seen,
                "frames_required": cls._required_frames(
                    pending.source,
                    runtime_settings,
                ),
                "current_stock": pending.current_stock,
                "source": pending.source,
            }
            for item_id, pending in sorted(state.pending_updates.items())
            if item_id in item_by_id
        ]

        logger.info(
            "Camera %s updated %s items, %s status changes, %s pending confirmations",
            camera_id,
            len(updated_items),
            len(status_changes),
            len(pending_status_updates),
        )

        return {
            "updated_items": updated_items,
            "status_changes": status_changes,
            "pending_status_updates": pending_status_updates,
            "detection_counts": {
                item_by_id[item_id].name: count
                for item_id, count in detection_counts.items()
                if item_id in item_by_id
            },
            "matched_detection_labels": sorted(matched_detection_labels),
            "unmatched_detection_labels": sorted(unmatched_detection_labels),
        }


stock_service = StockService()
