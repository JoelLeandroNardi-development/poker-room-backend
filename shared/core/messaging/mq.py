from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class RabbitConfig:
    url: Optional[str]
    exchange_name: str

    @staticmethod
    def from_env(required: bool = False) -> "RabbitConfig":
        url = os.getenv("RABBIT_URL")
        if required and not url:
            raise RuntimeError("RABBIT_URL environment variable is not set")

        exchange_name = os.getenv("EXCHANGE_NAME", "domain_events").strip()
        if not exchange_name:
            exchange_name = "domain_events"

        return RabbitConfig(url=url, exchange_name=exchange_name)

class RabbitPublisher:
    def __init__(self, cfg: RabbitConfig):
        self.cfg = cfg
        self.enabled = bool(cfg.url)
        self._conn: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.Exchange | None = None

    async def start(self) -> None:
        if not self.enabled:
            return

        if self._conn and not self._conn.is_closed and self._exchange is not None:
            return

        try:
            self._conn = await aio_pika.connect_robust(self.cfg.url)
            self._channel = await self._conn.channel(publisher_confirms=True)
            self._exchange = await self._channel.declare_exchange(
                self.cfg.exchange_name,
                ExchangeType.TOPIC,
                durable=True,
            )
            logger.info("publisher ready exchange=%s", self.cfg.exchange_name)
        except Exception as e:
            logger.warning(
                "publisher.start() failed (will retry on publish): %s: %s",
                type(e).__name__, e,
            )
            await self.close()

    async def close(self) -> None:
        try:
            if self._channel and not self._channel.is_closed:
                await self._channel.close()
        except Exception:
            pass
        finally:
            self._channel = None
            self._exchange = None

        try:
            if self._conn and not self._conn.is_closed:
                await self._conn.close()
        except Exception:
            pass
        finally:
            self._conn = None

    async def _ensure_ready(self) -> None:
        if not self.enabled:
            raise RuntimeError("RabbitPublisher disabled (no RABBIT_URL)")

        if self._exchange is not None and self._conn is not None and not self._conn.is_closed:
            return

        self._conn = await aio_pika.connect_robust(self.cfg.url)
        self._channel = await self._conn.channel(publisher_confirms=True)
        self._exchange = await self._channel.declare_exchange(
            self.cfg.exchange_name,
            ExchangeType.TOPIC,
            durable=True,
        )
        logger.info("publisher reconnected exchange=%s", self.cfg.exchange_name)

    async def publish(
        self,
        *,
        routing_key: str,
        payload: dict,
        message_id: str | None = None,
        headers: dict | None = None,
        mandatory: bool = True,
    ) -> None:
        if not self.enabled:
            return

        rk = (routing_key or "").strip()
        if not rk:
            raise ValueError("routing_key is required")

        await self._ensure_ready()
        if self._exchange is None:
            raise RuntimeError("Exchange is not initialized after _ensure_ready")

        body = json.dumps(payload, separators=(",", ":"), default=str, ensure_ascii=False).encode("utf-8")
        msg = Message(
            body=body,
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=message_id,
            headers=headers or {},
        )

        try:
            await self._exchange.publish(msg, routing_key=rk, mandatory=mandatory)
            logger.debug(
                "published exchange=%s rk=%s message_id=%s",
                self.cfg.exchange_name, rk, message_id,
            )
        except Exception as e:
            logger.error(
                "publish failed exchange=%s rk=%s message_id=%s err=%s: %s",
                self.cfg.exchange_name, rk, message_id, type(e).__name__, e,
            )
            raise

def create_publisher(*, required: bool = True):
    cfg = RabbitConfig.from_env(required=required)
    pub = RabbitPublisher(cfg)
    return pub, cfg
