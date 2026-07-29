from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol


SignalKind = Literal["cancel", "event"]


@dataclass(frozen=True)
class RuntimeSignal:
    kind: SignalKind
    execution_id: str
    sequence: int | None = None


class RuntimeNotifier(Protocol):
    """Best-effort wakeups; RuntimeStore remains the source of truth."""

    async def publish_cancel(self, execution_id: str) -> None: ...

    async def publish_event(
        self,
        execution_id: str,
        sequence: int,
    ) -> None: ...

    def subscribe(
        self,
        execution_id: str,
    ) -> AsyncIterator[RuntimeSignal]: ...

    async def close(self) -> None: ...

    async def validate_ready(self) -> dict: ...


class RedisRuntimeNotifier:
    """Redis Pub/Sub acceleration with fail-open PostgreSQL polling fallback."""

    def __init__(
        self,
        client,
        *,
        channel_prefix: str = "qidian:agent-runtime",
    ) -> None:
        self._client = client
        self._prefix = channel_prefix.rstrip(":")

    @classmethod
    async def open(
        cls,
        url: str,
        *,
        channel_prefix: str = "qidian:agent-runtime",
    ) -> "RedisRuntimeNotifier":
        if not url:
            raise ValueError("Redis URL is required for runtime coordination")
        from redis.asyncio import Redis

        client = Redis.from_url(
            url,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
        )
        await client.ping()
        return cls(client, channel_prefix=channel_prefix)

    def _channel(self, execution_id: str) -> str:
        return f"{self._prefix}:{execution_id}"

    async def _publish(self, signal: RuntimeSignal) -> None:
        payload = json.dumps(
            {
                "kind": signal.kind,
                "execution_id": signal.execution_id,
                "sequence": signal.sequence,
            },
            separators=(",", ":"),
        )
        try:
            await self._client.publish(
                self._channel(signal.execution_id),
                payload,
            )
        except Exception:
            # PostgreSQL state and polling are authoritative. Redis outages
            # may increase wakeup latency but cannot change run correctness.
            return

    async def publish_cancel(self, execution_id: str) -> None:
        await self._publish(RuntimeSignal("cancel", execution_id))

    async def publish_event(
        self,
        execution_id: str,
        sequence: int,
    ) -> None:
        await self._publish(
            RuntimeSignal("event", execution_id, sequence=sequence)
        )

    async def subscribe(
        self,
        execution_id: str,
    ) -> AsyncIterator[RuntimeSignal]:
        pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        try:
            await pubsub.subscribe(self._channel(execution_id))
            while True:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                except Exception:
                    await asyncio.sleep(0.25)
                    continue
                if not message:
                    continue
                try:
                    payload = json.loads(message["data"])
                    signal = RuntimeSignal(
                        kind=payload["kind"],
                        execution_id=payload["execution_id"],
                        sequence=payload.get("sequence"),
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue
                if signal.execution_id == execution_id:
                    yield signal
        finally:
            await pubsub.aclose()

    async def validate_ready(self) -> dict:
        await self._client.ping()
        return {"kind": "redis", "ready": True}

    async def close(self) -> None:
        await self._client.aclose()

