from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.models import HandLedgerEntry

async def get_ledger_entries(db: AsyncSession, round_id: str) -> list[HandLedgerEntry]:
    res = await db.execute(
        select(HandLedgerEntry)
        .where(HandLedgerEntry.round_id == round_id)
        .order_by(HandLedgerEntry.id.asc())
    )
    return list(res.scalars().all())

async def get_ledger_entry_by_id(db: AsyncSession, entry_id: str) -> HandLedgerEntry | None:
    res = await db.execute(
        select(HandLedgerEntry)
        .where(HandLedgerEntry.entry_id == entry_id)
    )
    return res.scalar_one_or_none()