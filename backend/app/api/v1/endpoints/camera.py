import base64
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.api.v1.endpoints.auth import authenticate_websocket
from app.services.alert_service import alert_service
from app.services.demo_frame_source_service import demo_frame_source_service
from app.services.stock_service import stock_service
from app.services.yolov8_service import yolov8_service

router = APIRouter()
logger = logging.getLogger(__name__)


def resolve_predicted_count(detection):
    try:
        count = int(detection.get("predicted_count", 1))
    except (TypeError, ValueError):
        return 1
    return max(1, count)


def build_sync_message(detections, result):
    pending_updates = result["pending_status_updates"]
    matched_labels = result["matched_detection_labels"]
    unmatched_labels = result["unmatched_detection_labels"]

    if not detections:
        if pending_updates:
            return (
                "Empty frame synced. Out-of-stock confirmation is pending for "
                f"{len(pending_updates)} item(s)."
            )
        return "Empty frame synced. No confirmed stock change yet."

    if unmatched_labels and not matched_labels:
        return (
            "Current frame only contains unmatched labels. No out-of-stock "
            "inference was applied."
        )

    if pending_updates:
        return (
            "State change candidates recorded. Waiting for consecutive frame "
            f"confirmation on {len(pending_updates)} item(s)."
        )

    return None


def bounded_int(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


async def build_detection_response(db, *, detections, camera_id, sync_inventory):
    sync_result = None

    if sync_inventory:
        result = stock_service.process_detections(
            db=db,
            detections=detections,
            camera_id=camera_id,
        )

        if result["status_changes"]:
            await alert_service.process_status_changes(
                db=db,
                status_changes=result["status_changes"],
            )

        sync_result = {
            "updated_items": len(result["updated_items"]),
            "status_changes": len(result["status_changes"]),
            "pending_updates": result["pending_status_updates"],
            "pending_status_count": len(result["pending_status_updates"]),
            "detection_counts": result["detection_counts"],
            "matched_labels": result["matched_detection_labels"],
            "unmatched_labels": result["unmatched_detection_labels"],
            "message": build_sync_message(detections, result),
        }

    total_predicted_count = sum(resolve_predicted_count(det) for det in detections)

    return {
        "type": "detection",
        "camera_id": camera_id,
        "boxes": detections,
        "count": len(detections),
        "total_predicted_count": total_predicted_count,
        "sync_inventory": sync_inventory,
        "sync_result": sync_result,
    }


@router.websocket("/stream")
async def camera_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time camera streaming and YOLOv8 inference
    Receives video frames, runs detection, updates stock, and returns results
    """
    from app.db.database import SessionLocal

    db = SessionLocal()
    demo_session = None
    demo_detection_cache = {}

    try:
        current_user = authenticate_websocket(websocket, db)
        await websocket.accept()
        logger.info(
            "Camera stream connection established for user %s",
            current_user.username,
        )

        while True:
            message = await websocket.receive_text()
            data = json.loads(message)

            if data.get("type") == "frame":
                image_data = data.get("image")
                sync_inventory = bool(data.get("sync_inventory"))
                camera_id = str(data.get("camera_id") or "camera_1")

                if image_data:
                    if "," in image_data:
                        image_data = image_data.split(",")[1]

                    image_bytes = base64.b64decode(image_data)
                    detection_started_at = time.perf_counter()
                    detections = await run_in_threadpool(
                        yolov8_service.detect,
                        image_bytes,
                    )
                    processing_ms = round(
                        (time.perf_counter() - detection_started_at) * 1000
                    )

                    response = await build_detection_response(
                        db,
                        detections=detections,
                        camera_id=camera_id,
                        sync_inventory=sync_inventory,
                    )
                    response["processing_ms"] = processing_ms
                    await websocket.send_json(response)

            elif data.get("type") == "demo_frame":
                sync_inventory = bool(data.get("sync_inventory", True))
                camera_id = str(data.get("camera_id") or "demo_dataset")

                if demo_session is None or bool(data.get("reset")):
                    demo_session = demo_frame_source_service.create_session(
                        source=str(data.get("source") or "test"),
                        max_images=bounded_int(data.get("max_images"), 20, 1, 100),
                        seed=bounded_int(data.get("seed"), 20260519, 0, 999999999),
                        repeat_min=bounded_int(data.get("repeat_min"), 5, 1, 30),
                        repeat_max=bounded_int(data.get("repeat_max"), 10, 1, 30),
                        empty_interval=bounded_int(data.get("empty_interval"), 5, 0, 100),
                        empty_frames=bounded_int(data.get("empty_frames"), 3, 0, 30),
                    )
                    demo_detection_cache = {}

                frame = demo_session.next_frame()
                cached_detection = False

                if frame.kind == "empty":
                    detections = []
                    processing_ms = 0
                elif frame.cache_key in demo_detection_cache:
                    detections = [dict(det) for det in demo_detection_cache[frame.cache_key]]
                    processing_ms = 0
                    cached_detection = True
                else:
                    detection_started_at = time.perf_counter()
                    detections = await run_in_threadpool(
                        yolov8_service.detect,
                        frame.image_bytes,
                    )
                    processing_ms = round(
                        (time.perf_counter() - detection_started_at) * 1000
                    )
                    if frame.cache_key:
                        demo_detection_cache[frame.cache_key] = [dict(det) for det in detections]

                response = await build_detection_response(
                    db,
                    detections=detections,
                    camera_id=camera_id,
                    sync_inventory=sync_inventory,
                )
                response.update(
                    {
                        "processing_ms": processing_ms,
                        "image": frame.image_data_url,
                        "image_name": frame.image_name,
                        "demo_frame_kind": frame.kind,
                        "frame_index": frame.frame_index,
                        "cached_detection": cached_detection,
                        "demo_frame_count": demo_session.frame_count,
                        "demo_image_count": demo_session.image_count,
                    }
                )
                await websocket.send_json(response)

            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("Client disconnected from camera stream")
    except Exception as exc:
        logger.error("Camera stream error: %s", exc)
    finally:
        db.close()
