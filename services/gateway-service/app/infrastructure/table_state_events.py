from __future__ import annotations

import asyncio
import logging

import aio_pika

from shared.core.messaging.consumer import run_consumer_with_retry_dlq

from .table_state_fanout import TableStateEventFanout, table_state_fanout
from .. import config

logger = logging.getLogger(__name__)

class TableStateEventConsumer:
    def __init__(
        self,
        *,
        fanout: TableStateEventFanout = table_state_fanout,
    ) -> None:
        self.fanout = fanout
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None

    @property
    def enabled(self) -> bool:
        return bool(config.RABBIT_URL and config.TABLE_STATE_EVENT_ROUTING_KEYS)

    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        self._stop_event.set()

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None

    async def _run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._consume_until_stopped()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "table-state event consumer disconnected: %s: %s",
                    type(exc).__name__,
                    exc,
                )

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                continue

    async def _consume_until_stopped(self) -> None:
        if not config.RABBIT_URL:
            return

        connection = await aio_pika.connect_robust(config.RABBIT_URL)
        self._connection = connection

        try:
            channel = await connection.channel()
            queue_name = config.TABLE_STATE_EVENT_CONSUMER_QUEUE
            await run_consumer_with_retry_dlq(
                channel=channel,
                exchange_name=config.EXCHANGE_NAME,
                queue_name=queue_name,
                retry_queue=f"{queue_name}.retry",
                dlq_queue=f"{queue_name}.dlq",
                routing_keys=config.TABLE_STATE_EVENT_ROUTING_KEYS,
                handler=self.fanout.handle_event,
                retry_delay_ms=config.TABLE_STATE_EVENT_RETRY_DELAY_MS,
                max_retries=config.TABLE_STATE_EVENT_MAX_RETRIES,
                service_label=config.SERVICE_NAME,
            )

            await self._stop_event.wait()
        finally:
            if not connection.is_closed:
                await connection.close()
            if self._connection is connection:
                self._connection = None

table_state_event_consumer = TableStateEventConsumer()