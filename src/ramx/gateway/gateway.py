from __future__ import annotations

import asyncio
import logging
import platform
import sys
import time
from collections.abc import Sequence
from typing import Annotated, Any, Final

import msgspec
from aiohttp import ClientSession
from msgspec import Meta, Struct
from yarl import URL

from ._payload import GatewayPayload, OpCode
from ._transport import GatewayTransport

__all__: Sequence[str] = ("Gateway", "ShardInfo")

LIBRARY_NAME: Final[str] = sys.intern("discord-ram")


class ConnectionProperties(Struct):
    system: str = msgspec.field(name="os")
    browser: str
    device: str


class ShardInfo(Struct, array_like=True):
    shard_id: int
    shard_count: int


class Identify(Struct, omit_defaults=True):
    token: str
    properties: ConnectionProperties
    compress: bool = False
    large_threshold: Annotated[int, Meta(ge=50, le=250)] | None = None
    shard: ShardInfo | None = None
    intents: int | None = None


class Gateway:
    _logger: logging.Logger = logging.getLogger("ram.gateway")

    def __init__(
        self,
        url: str,
        token: str,
        *,
        shard_id: int | None = None,
        shard_count: int | None = None,
        large_threshold: int = 50,
        client_session: ClientSession | None = None,
        transport_compression: bool = False,
        browser: str = LIBRARY_NAME,
    ) -> None:
        self._client_session: ClientSession | None = client_session
        self._transport_compression: bool = transport_compression
        self._ws: GatewayTransport | None = None

        self._gateway_url: str = url
        self._resume_gateway_url: str | None = None
        self._seq: int | None = None

        self._stop_event: asyncio.Event = asyncio.Event()

        self._heartbeat_interval: float = float("NaN")
        self._last_heartbeat_ack: float = float("NaN")
        self._last_heartbeat_sent: float = float("NaN")

        self._token: str = token
        self._browser: str = browser

        self.intents: int = 0

        self.shard_id: int | None = shard_id
        self.shard_count: int | None = shard_count

        self.large_threshold: int = large_threshold

        if self.shard_info:
            self._logger = self._logger.getChild(str(self.shard_id))

    @property
    def _identify(self) -> Identify:
        return Identify(
            token=self._token,
            properties=ConnectionProperties(system=platform.system(), browser=self._browser, device=LIBRARY_NAME),
            compress=self._transport_compression,
            large_threshold=self.large_threshold,
            shard=self.shard_info,
            intents=self.intents,
        )

    @property
    def shard_info(self) -> ShardInfo | None:
        if self.shard_id is not None and self.shard_count is not None:
            return ShardInfo(self.shard_id, self.shard_count)
        return None

    @property
    def heartbeat_latency(self) -> float:
        return self._last_heartbeat_ack - self._last_heartbeat_sent

    async def _heartbeat(self) -> None:
        assert self._ws
        await self._ws.send(GatewayPayload(op=OpCode.HEARTBEAT, d=self._seq))
        self._logger.debug("send heartbeat [s:%s]", self._seq)
        self._last_heartbeat_sent = time.monotonic()

    async def _heartbeat_task(self) -> None:
        assert self._ws
        self._logger.debug("starting heartbeat with %ss interval", self._heartbeat_interval)
        while not self._stop_event.is_set():
            if self._last_heartbeat_ack <= self._last_heartbeat_sent:
                self._logger.error("zombie connection")
                return
            await self._heartbeat()
            await asyncio.sleep(self._heartbeat_interval)

    async def _poll_events_task(self) -> None:
        assert self._ws
        async for payload in self._ws.receive():
            self._logger.debug("received [op:%s]", payload.op)
            if payload.op == OpCode.DISPATCH:
                assert payload.s
                self._seq = payload.s
            elif payload.op == OpCode.HEARTBEAT_ACK:
                now = time.monotonic()
                self._last_heartbeat_ack = now
            elif payload.op == OpCode.HEARTBEAT:
                await self._heartbeat()
            else:
                self._logger.error("unknown op code [%s]", payload)

    async def connect(self) -> None:
        url_query: dict[str, Any] = {"v": 10, "encoding": "json"}  # TODO: Replace magic value with variable/argument
        if self._transport_compression:
            url_query["compress"] = "zlib-stream"
        self._ws = await GatewayTransport.connect(
            URL(self._resume_gateway_url or self._gateway_url).with_query(url_query),
            client_session=self._client_session,
            transport_compression=self._transport_compression,
        )
        payload: GatewayPayload = await self._ws.receive_payload()

        if payload.op == OpCode.RECONNECT:
            print("TODO: reconnect")  # TODO(connect): Reconnect

        if payload.op != OpCode.HELLO:
            self._logger.error("excepted hello, but received [op:%s], closing...", payload.op)
            await self.close()

        assert payload.d is not None
        self._heartbeat_interval = payload.d["heartbeat_interval"] / 1_000.0
        self._logger.debug("connected, heartbeat interval %s s", self._heartbeat_interval)

        asyncio.create_task(self._heartbeat_task(), name="heartbeat")
        asyncio.create_task(self._poll_events_task(), name="poll events")

        await self._ws.send(GatewayPayload(op=OpCode.IDENTIFY, d=self._identify))
        await self._stop_event.wait()  # TODO(runtime): Rework connect + Graceful shutdown

    async def close(self) -> None:
        self._stop_event.set()
        # TODO(runtime)(self._ws.send_close): Graceful shutdown
