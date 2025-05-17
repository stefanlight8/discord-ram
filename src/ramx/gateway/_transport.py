from __future__ import annotations

import asyncio
import logging
import typing
import zlib
from collections.abc import Sequence
from contextlib import AsyncExitStack

from aiohttp import ClientSession, ClientWebSocketResponse, WSMessage, WSMsgType
from aiohttp.typedefs import StrOrURL
from msgspec import json

from ._payload import GatewayPayload

__all__: Sequence[str] = ("GatewayTransport",)

ZLIB_SUFFIX: typing.Final[bytes] = b"\x00\x00\xff\xff"


@typing.final
class GatewayTransport:
    _logger: logging.Logger = logging.getLogger("ram.websocket")

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
        return cls(connection, exit_stack, transport_compression=transport_compression)

    def __init__(
        self, connection: ClientWebSocketResponse, exit_stack: AsyncExitStack, *, transport_compression: bool
    ) -> None:
        self.connection: ClientWebSocketResponse = connection
        self.transport_compression: bool = transport_compression

        self._exit_stack: AsyncExitStack = exit_stack
        self._stop_event: asyncio.Event = asyncio.Event()

        self._decoder: json.Decoder = json.Decoder(GatewayPayload)
        self._encoder: json.Encoder = json.Encoder()

        self._inflator: zlib._Decompress | None = zlib.decompressobj() if self.transport_compression else None
        self._buffer: bytearray = bytearray()

    async def send(self, payload: GatewayPayload) -> None:
        self._logger.debug("send payload [%r]", payload)
        await self.connection.send_bytes(data=self._encoder.encode(payload))

    async def receive_stream(self, data: memoryview[int] | bytes) -> GatewayPayload:
        assert self._inflator is not None
        self._buffer.extend(data)
        while not self._buffer.endswith(ZLIB_SUFFIX):
            data = await self.connection.receive_bytes()
            self._buffer.extend(data)
        data = self._inflator.decompress(self._buffer)
        payload = self._decoder.decode(memoryview(data))
        self._buffer.clear()
        return payload

    async def receive_payload(self) -> GatewayPayload:
        if self.transport_compression:
            data: memoryview[int] = memoryview(await self.connection.receive_bytes())
            payload = await self.receive_stream(data)
        else:
            payload = self._decoder.decode(await self.connection.receive_str())
        self._logger.debug("received [%r]", payload)
        return payload

    async def receive(self) -> typing.AsyncIterator[GatewayPayload]:
        while not self._stop_event.is_set():
            message: WSMessage = await self.connection.receive()
            if message.type == WSMsgType.ERROR:
                raise Exception("websocket error", message.extra, message.data)

            if message.type == WSMsgType.BINARY and self.transport_compression:
                payload = await self.receive_stream(message.data)
            elif message.type == WSMsgType.TEXT and not self.transport_compression:
                payload = self._decoder.decode(message.data)
            else:
                raise Exception("unknown message", message)

            self._logger.debug("received [%r]", payload)
            yield payload
