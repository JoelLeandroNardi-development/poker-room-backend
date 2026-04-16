from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Iterable

import aio_pika
from aio_pika import ExchangeType, Message, DeliveryMode

logger = logging.getLogger(__name__)

Handler = Callable[[dict], Awaitable[None]]

async def setup_consumer_topology(
    *,
    channel: aio_pika.abc.AbstractChannel,
    exchange_name: str,
    queue_name: str,
    retry_queue: str,
    dlq_queue: str,
    routing_keys: Iterable[str],
    retry_delay_ms: int,
    prefetch: int = 50,
) -> tuple[aio_pika.Exchange, aio_pika.Queue]:
    await channel.set_qos(prefetch_count=prefetch)

    exchange = await channel.declare_exchange(
        exchange_name,
        ExchangeType.TOPIC,
        durable=True,
    )

    main_queue = await channel.declare_queue(
        queue_name,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": dlq_queue,
        },
    )

    await channel.declare_queue(
        retry_queue,
        durable=True,
        arguments={
            "x-message-ttl": retry_delay_ms,
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": queue_name,
        },
    )

    await channel.declare_queue(dlq_queue, durable=True)

    rks = list(routing_keys)
    for rk in rks:
        await main_queue.bind(exchange, routing_key=rk)

    return exchange, main_queue

def _safe_decode_json(message: aio_pika.IncomingMessage) -> dict:
    if not message.body:
        return {}
    try:
        return json.loads(message.body.decode("utf-8"))
    except Exception:
        return {}

async def run_consumer_with_retry_dlq(
    *,
    channel: aio_pika.abc.AbstractChannel,
    exchange_name: str,
    queue_name: str,
    retry_queue: str,
    dlq_queue: str,
    routing_keys: list[str],
    handler: Handler,
    retry_delay_ms: int = 5000,
    max_retries: int = 3,
    prefetch: int = 50,
    service_label: str = "service",
) -> None:
    await setup_consumer_topology(
        channel=channel,
        exchange_name=exchange_name,
        queue_name=queue_name,
        retry_queue=retry_queue,
        dlq_queue=dlq_queue,
        routing_keys=routing_keys,
        retry_delay_ms=retry_delay_ms,
        prefetch=prefetch,
    )

    main_queue = await channel.get_queue(queue_name, ensure=False)

    logger.info(
        "[%s] consuming queue=%s exchange=%s routing_keys=%s retry=%s dlq=%s",
        service_label, queue_name, exchange_name, routing_keys, retry_queue, dlq_queue,
    )

    async def _on_message(message: aio_pika.IncomingMessage):
        try:
            payload = _safe_decode_json(message)
            await handler(payload)
            await message.ack()
        except Exception as e:
            headers_in = dict(message.headers or {})
            retry_count = int(headers_in.get("x-retry-count", 0) or 0)

            if retry_count >= max_retries:
                logger.error("[%s] Poison -> DLQ: %s: %s", service_label, type(e).__name__, e)
                await message.reject(requeue=False)
                return

            headers_in["x-retry-count"] = retry_count + 1

            retry_msg = Message(
                body=message.body,
                headers=headers_in,
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type=message.content_type or "application/json",
            )

            await message.channel.default_exchange.publish(retry_msg, routing_key=retry_queue)
            logger.warning("[%s] retry #%d", service_label, retry_count + 1)

            await message.ack()

    await main_queue.consume(_on_message)
