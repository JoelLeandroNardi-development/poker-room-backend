from __future__ import annotations

def add_outbox_event(db, OutboxEvent, event: dict) -> None:
    db.add(
        OutboxEvent(
            event_id=event["event_id"],
            event_type=event["event_type"],
            routing_key=event["event_type"],
            payload=event,
            status="PENDING",
        )
    )
