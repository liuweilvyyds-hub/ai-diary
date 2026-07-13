"""Memory management routes."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db, PersonalMemory
from services.memory_service import generate_memory_candidates
from services.helpers import memory_to_dict

router = APIRouter(prefix="/api", tags=["memories"])


@router.get("/memories")
def list_memories(active: Optional[bool] = Query(True), category: Optional[str] = Query(None),
                   db: Session = Depends(get_db)):
    query = db.query(PersonalMemory)
    if active is not None:
        query = query.filter(PersonalMemory.active == (1 if active else 0))
    if category:
        query = query.filter(PersonalMemory.category == category)
    memories = query.order_by(PersonalMemory.pinned.desc(), PersonalMemory.updated_at.desc()).all()
    return {"memories": [memory_to_dict(m) for m in memories], "total": len(memories)}


@router.post("/memories")
def create_memory(memory: dict = Body(...), db: Session = Depends(get_db)):
    content = memory.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content required")
    m = PersonalMemory(
        category=(memory.get("category") or "general").strip()[:80],
        content=content,
        source=(memory.get("source") or "manual").strip()[:80],
        confidence=max(0.0, min(float(memory.get("confidence", 1.0)), 1.0)),
        pinned=1 if memory.get("pinned") else 0,
        active=1,
        created_at=datetime.now(), updated_at=datetime.now(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return memory_to_dict(m)


@router.post("/memories/candidates")
def suggest_memory_candidates(req: dict = Body(default={}), db: Session = Depends(get_db)):
    days = int((req or {}).get("days", 7))
    candidates = generate_memory_candidates(db, days)
    return {"candidates": candidates, "total": len(candidates)}


@router.put("/memories/{memory_id}")
def update_memory(memory_id: int, update: dict = Body(...), db: Session = Depends(get_db)):
    m = db.query(PersonalMemory).filter(PersonalMemory.id == memory_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    if update.get("category") is not None:
        m.category = (update["category"] or "general").strip()[:80]
    if update.get("content") is not None:
        content = update["content"].strip()
        if not content:
            raise HTTPException(status_code=400, detail="content required")
        m.content = content
    if update.get("confidence") is not None:
        m.confidence = max(0.0, min(float(update["confidence"]), 1.0))
    if update.get("pinned") is not None:
        m.pinned = 1 if update["pinned"] else 0
    if update.get("active") is not None:
        m.active = 1 if update["active"] else 0
    m.updated_at = datetime.now()
    db.commit()
    db.refresh(m)
    return memory_to_dict(m)


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: int, db: Session = Depends(get_db)):
    m = db.query(PersonalMemory).filter(PersonalMemory.id == memory_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    m.active = 0
    m.updated_at = datetime.now()
    db.commit()
    return {"ok": True}
