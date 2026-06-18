from __future__ import annotations
from fastapi import APIRouter
from backend.db import db
from backend.db.queries import templates as tq

router = APIRouter(prefix="/api/templates", tags=["templates"])

@router.get("")
async def list_templates():
    return await tq.list_templates(db.pool)
