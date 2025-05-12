from __future__ import annotations

import asyncio
import logging
import platform
import sys
import time
import typing
import zlib
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AsyncExitStack
from typing import Any, Final

from aiohttp import ClientSession, ClientWebSocketResponse, WSMessage, WSMsgType
from aiohttp.typedefs import StrOrURL
from msgspec import Struct, json
from yarl import URL

__all__: Sequence[str] = ("Gateway",)

_LOGGER: logging.Logger = logging.getLogger("ram.ws")

_DISPATCH: Final[int] = 0
_HEARTBEAT: Final[int] = 1
_IDENTIFY: Final[int] = 2
_RESUME: Final[int] = 6
_RECONNECT: Final[int] = 7
_REQUEST_GUILD_MEMBERS: Final[int] = 8
_INVALID_SESSION: Final[int] = 9
_HELLO: Final[int] = 10
_HEARTBEAT_ACK: Final[int] = 11

LIBRARY_NAME: Final[str] = sys.intern("discord-ram")
IDENTIFY_PROPERTIES: Final[Mapping[str, Any]] = {
    "os": platform.system(),
    "browser": LIBRARY_NAME,
    "device": LIBRARY_NAME,
}

ZLIB_SUFFIX: Final[bytes] = b"\x00\x00\xff\xff"

NAN: Final[float] = float("NaN")


class GatewayPayload(Struct):
    op: int
    d: Any | None = None
    s: int | None = None
    t: str | None = None


@typing.final
class GatewayTransport:
    @classmethod
    async def connect(
        cls, url: StrOrURL, *, client_session: ClientSession | None = None, transport_compression: bool = False
    ) -> GatewayTransport:
        exit_stack: AsyncExitStack = AsyncExitStack()
        if client_session is None:
            client_session = ClientSession()
            await exit_stack.enter_async_context(client_session)
        connection = await exit_stack.enter_async_context(
            client_session.ws_connect(url, max_msg_size=0, autoclose=False)
        )
        return cls(connection, exit_stack, transport_compression)

    def __init__(
        self, connection: ClientWebSocketResponse, exit_stack: AsyncExitStack, transport_compression: bool
    ) -> None:
        self.connection: ClientWebSocketResponse = connection
        self.exit_stack: AsyncExitStack = exit_stack
        self.transport_compression: bool = transport_compression
        self._stop_event: asyncio.Event = asyncio.Event()
        self._zlib = zlib.decompressobj()
        self._buffer: bytearray = bytearray()

    async def send(self, payload: GatewayPayload) -> None:
        _LOGGER.debug("send payload [op:%s]", payload.op)
        await self.connection.send_str(data=json.encode(payload).decode())

    async def receive_stream(self, data: bytes) -> GatewayPayload:
        self._buffer.extend(data)
        while not self._buffer.endswith(ZLIB_SUFFIX):
            data = await self.connection.receive_bytes()
            self._buffer.extend(data)
        data = self._zlib.decompress(self._buffer)
        payload = json.decode(memoryview(data), type=GatewayPayload)
        self._buffer.clear()
        return payload

    async def receive_payload(self) -> GatewayPayload:
        if self.transport_compression:
            payload: GatewayPayload = await self.receive_stream(await self.connection.receive_bytes())
        else:
            data: str = await self.connection.receive_str()
            payload = json.decode(memoryview(data.encode()), type=GatewayPayload)
        _LOGGER.debug("received payload [op:%s,s:%s,t:%s]", payload.op, payload.s, payload.t)
        return payload

    async def receive(self) -> AsyncIterator[GatewayPayload]:
        while not self._stop_event.is_set():
            message: WSMessage = await self.connection.receive()
            if message.type == WSMsgType.BINARY and self.transport_compression:
                yield await self.receive_stream(message.data)
            elif message.type == WSMsgType.TEXT and not self.transport_compression:
                payload: GatewayPayload = json.decode(memoryview(message.data.encode()), type=GatewayPayload)
                yield payload
            else:
                raise Exception()  # TODO(websocket)(self.send_close): Protocol error


class Gateway:
    def __init__(
        self,
        url: str,
        token: str,
        *,
        shard_id: int | None = None,
        shard_count: int | None = None,
        large_threshold: int = 250,
        client_session: ClientSession | None = None,
        transport_compression: bool = False,
    ) -> None:
        self._logger: logging.Logger = logging.getLogger(
            "ram.gateway%s" % (f".{shard_id}" if shard_id is not None else "")
        )

        self._client_session: ClientSession | None = client_session
        self._transport_compression: bool = transport_compression
        self._ws: GatewayTransport | None = None

        self._gateway_url: str = url
        self._resume_gateway_url: str | None = None
        self._seq: int | None = None

        self._stop_event: asyncio.Event = asyncio.Event()

        self._heartbeat_interval: float = NAN
        self._last_heartbeat_ack: float = NAN
        self._last_heartbeat_sent: float = NAN

        self._token: str = token
        self._intents: int = 0

        self.shard_id: int | None = shard_id
        self.shard_count: int | None = shard_count

        self.large_threshold: int = large_threshold

    @property
    def _identify(self) -> Mapping[str, Any]:
        return {
            "token": self._token,
            "intents": self._intents,
            "properties": IDENTIFY_PROPERTIES,
            "large_threshold": self.large_threshold,
            "compression": self._transport_compression,
            **(
                {"shard": [self.shard_id, self.shard_count]}
                if self.shard_id is not None and self.shard_count is not None
                else {}
            ),
        }

    @property
    def heartbeat_latency(self) -> float:
        return self._last_heartbeat_ack - self._last_heartbeat_sent

    async def _heartbeat_task(self) -> None:
        assert self._ws
        self._logger.debug("starting heartbeat with %ss interval", self._heartbeat_interval)
        while not self._stop_event.is_set():
            if self._last_heartbeat_ack <= self._last_heartbeat_sent:
                self._logger.error("zombie connection")
                return

            await self._ws.send(GatewayPayload(op=_HEARTBEAT, d=self._seq))
            self._logger.debug("send heartbeat [s:%s]", self._seq)
            self._last_heartbeat_sent = time.monotonic()

            await asyncio.sleep(self._heartbeat_interval)

    async def _poll_events_task(self) -> None:
        assert self._ws
        async for payload in self._ws.receive():
            if payload.op == _DISPATCH:
                assert payload.s
                self._seq = payload.s
                self._logger.debug("received event: Dispatch [t:%s;s:%s]", payload.t, self._seq)
            elif payload.op == _HEARTBEAT_ACK:
                now = time.monotonic()
                self._last_heartbeat_ack = now
                self._logger.debug("received HEARTBEAT ACK")
            else:
                self._logger.error(
                    "unknown op code [op:%s;d:%s,s:%s,t:%s]", payload.op, payload.d, payload.s, payload.t
                )

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

        if payload.op == _RECONNECT:
            print("TODO: reconnect")  # TODO(connect): Reconnect

        if payload.op != _HELLO:
            self._logger.error("excepted hello, but received [op:%s], closing...", payload.op)
            await self.close()

        assert payload.d is not None
        self._heartbeat_interval = payload.d["heartbeat_interval"] / 1_000.0
        self._logger.debug("connected, heartbeat interval %s s", self._heartbeat_interval)

        asyncio.create_task(self._heartbeat_task(), name="heartbeat")
        asyncio.create_task(self._poll_events_task(), name="poll events")

        await self._ws.send(GatewayPayload(op=_IDENTIFY, d=self._identify))
        await self._stop_event.wait()  # TODO(runtime): Rework connect + Graceful shutdown

    async def close(self) -> None:
        self._stop_event.set()
        # TODO(runtime)(self._ws.send_close): Graceful shutdown
