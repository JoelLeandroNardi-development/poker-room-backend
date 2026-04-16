from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

async def fetch_or_404(
    db: AsyncSession,
    model,
    *,
    filter_column,
    filter_value,
    detail: str = "Not found",
):
    res = await db.execute(select(model).where(filter_column == filter_value))
    obj = res.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=detail)
    return obj

def apply_partial_update(entity, data, fields: list[str]) -> None:
    for field in fields:
        value = getattr(data, field, None)
        if value is not None:
            setattr(entity, field, value)
