from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Sequence

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

async def _claim_batch(
    db: AsyncSession, OutboxEvent, batch_size: int
) -> Sequence:
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.status == "PENDING")
        .order_by(OutboxEvent.id.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())

async def _mark_sent(db: AsyncSession, OutboxEvent, row_id: int) -> None:
    await db.execute(
        update(OutboxEvent)
        .where(OutboxEvent.id == row_id)
        .values(
            status="SENT",
            published_at=dt.datetime.now(dt.timezone.utc),
            last_error=None,
        )
    )

async def _mark_failure(
    db: AsyncSession,
    OutboxEvent,
    row_id: int,
    attempts: int,
    err: str,
    max_attempts: int,
) -> None:
    new_status = "FAILED" if attempts >= max_attempts else "PENDING"
    await db.execute(
        update(OutboxEvent)
        .where(OutboxEvent.id == row_id)
        .values(
            status=new_status,
            attempts=attempts,
            last_error=(err or "")[:500],
        )
    )

async def make_outbox_stats(SessionLocal, OutboxEvent) -> dict:
    async with SessionLocal() as db:
        res = await db.execute(
            select(OutboxEvent.status, func.count()).group_by(OutboxEvent.status)
        )
        rows = res.all()

    counts = {status: int(n) for status, n in rows}
    return {
        "type": "sql",
        "pending": counts.get("PENDING", 0),
        "failed": counts.get("FAILED", 0),
        "sent": counts.get("SENT", 0),
    }

async def run_outbox_loop(
    *,
    stop_event: asyncio.Event,
    SessionLocal,
    OutboxEvent,
    publisher,
    service_label: str = "service",
    max_attempts: int = 20,
    poll_interval: float = 1.0,
    batch_size: int = 50,
) -> None:
    await publisher.start()

    while not stop_event.is_set():
        try:
            async with SessionLocal() as db:
                async with db.begin():
                    batch = await _claim_batch(db, OutboxEvent, batch_size)
                    for ev in batch:
                        try:
                            await publisher.publish(
                                routing_key=ev.routing_key,
                                payload=ev.payload,
                                message_id=ev.event_id,
                            )
                            await _mark_sent(db, OutboxEvent, ev.id)
                        except Exception as e:
                            next_attempts = (ev.attempts or 0) + 1
                            await _mark_failure(
                                db, OutboxEvent, ev.id, next_attempts, str(e), max_attempts
                            )

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                continue

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("[%s] outbox worker loop error: %s: %s", service_label, type(e).__name__, e)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
