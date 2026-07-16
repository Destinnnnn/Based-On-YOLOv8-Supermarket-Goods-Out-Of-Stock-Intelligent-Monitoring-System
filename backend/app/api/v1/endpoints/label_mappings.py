from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_active_admin, get_current_user
from app.db.database import get_db
from app.models.item import Item
from app.models.label_mapping import LabelMapping
from app.models.user import User
from app.schemas.label_mapping import (
    LabelMappingCreate,
    LabelMappingResponse,
    LabelMappingUpdate,
)

router = APIRouter(dependencies=[Depends(get_current_user)])


def to_response(mapping: LabelMapping, item_name: str) -> LabelMappingResponse:
    return LabelMappingResponse(
        id=mapping.id,
        detection_label=mapping.detection_label,
        item_id=mapping.item_id,
        item_name=item_name,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    )


@router.get("/", response_model=list[LabelMappingResponse])
def read_label_mappings(db: Session = Depends(get_db)):
    mappings = (
        db.query(LabelMapping, Item.name)
        .join(Item, Item.id == LabelMapping.item_id)
        .order_by(LabelMapping.detection_label.asc())
        .all()
    )
    return [to_response(mapping, item_name) for mapping, item_name in mappings]


@router.post("/", response_model=LabelMappingResponse)
def create_label_mapping(
    mapping_in: LabelMappingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    detection_label = mapping_in.detection_label.strip()
    if not detection_label:
        raise HTTPException(status_code=400, detail="Detection label cannot be empty")

    item = db.query(Item).filter(Item.id == mapping_in.item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    existing = (
        db.query(LabelMapping)
        .filter(LabelMapping.detection_label == detection_label)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Detection label already mapped")

    mapping = LabelMapping(
        detection_label=detection_label,
        item_id=mapping_in.item_id,
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return to_response(mapping, item.name)


@router.patch("/{mapping_id}", response_model=LabelMappingResponse)
def update_label_mapping(
    mapping_id: int,
    mapping_in: LabelMappingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    mapping = db.query(LabelMapping).filter(LabelMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    if mapping_in.item_id is not None:
        item = db.query(Item).filter(Item.id == mapping_in.item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        mapping.item_id = item.id
    else:
        item = db.query(Item).filter(Item.id == mapping.item_id).first()

    if mapping_in.detection_label is not None:
        detection_label = mapping_in.detection_label.strip()
        if not detection_label:
            raise HTTPException(status_code=400, detail="Detection label cannot be empty")
        duplicate = (
            db.query(LabelMapping)
            .filter(
                LabelMapping.detection_label == detection_label,
                LabelMapping.id != mapping_id,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=400, detail="Detection label already mapped")
        mapping.detection_label = detection_label

    db.commit()
    db.refresh(mapping)
    return to_response(mapping, item.name if item else "")


@router.delete("/{mapping_id}")
def delete_label_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    mapping = db.query(LabelMapping).filter(LabelMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    db.delete(mapping)
    db.commit()
    return {"message": "Mapping deleted", "mapping_id": mapping_id}
