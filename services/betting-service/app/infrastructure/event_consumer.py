from __future__ import annotations

import aio_pika

from ..domain.constants import EventKey, GameEventType
from .config import (
    DEFAULT_MAX_RETRIES, DEFAULT_PREFETCH, DEFAULT_RETRY_DELAY_MS,
    DLQ_QUEUE, QUEUE_NAME, RETRY_QUEUE, ROUTING_KEYS,
    SERVICE_LOG_PREFIX, SERVICE_NAME,
)
from .messaging import EXCHANGE_NAME, RABBIT_URL, publisher
from shared.core.messaging.consumer import run_consumer_with_retry_dlq

async def process_event(payload: dict):
    event_type = payload.get(EventKey.EVENT_TYPE)

    if event_type not in ROUTING_KEYS:
        return

    if event_type == GameEventType.ROUND_STARTED:
        print(f"{SERVICE_LOG_PREFIX} Round started event received, ready for bets")

    elif event_type == GameEventType.ROUND_COMPLETED:
        print(f"{SERVICE_LOG_PREFIX} Round completed event received")

async def start_consumer():
    if not RABBIT_URL:
        raise RuntimeError("RABBIT_URL environment variable is not set")

    await publisher.start()

    conn = await aio_pika.connect_robust(RABBIT_URL)
    channel = await conn.channel()

    await run_consumer_with_retry_dlq(
        channel=channel,
        exchange_name=EXCHANGE_NAME,
        queue_name=QUEUE_NAME,
        retry_queue=RETRY_QUEUE,
        dlq_queue=DLQ_QUEUE,
        routing_keys=ROUTING_KEYS,
        handler=process_event,
        retry_delay_ms=DEFAULT_RETRY_DELAY_MS,
        max_retries=DEFAULT_MAX_RETRIES,
        prefetch=DEFAULT_PREFETCH,
        service_label=SERVICE_NAME,
    )

    print(f"{SERVICE_LOG_PREFIX} consumer started with DLQ + retry")
    return conn