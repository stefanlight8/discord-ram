from __future__ import annotations

import typing
from collections.abc import Sequence
from enum import Enum
from typing import Any

from msgspec import Struct

__all__: Sequence[str] = ("GatewayPayload", "OpCode")


@typing.final
class OpCode(int, Enum):
    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    RESUME = 6
    RECONNECT = 7
    REQUEST_GUILD_MEMBERS = 8
    INVALID_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11


class GatewayPayload(Struct):
    op: OpCode
    d: Any | None = None
    s: int | None = None
    t: str | None = None
