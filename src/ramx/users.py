from __future__ import annotations

from collections.abc import Sequence
from enum import Enum, IntFlag

import msgspec
from msgspec import Struct

__all__: Sequence[str] = ()


class UserFlag(IntFlag):
    NONE = 0
    STAFF = 1 << 0
    PARTNER = 1 << 1
    HYPESQUAD = 1 << 2
    BUG_HUNTER_LEVEL_1 = 1 << 3
    HYPESQUAD_ONLINE_HOUSE_1 = 1 << 6
    HYPESQUAD_ONLINE_HOUSE_2 = 1 << 7
    HYPESQUAD_ONLINE_HOUSE_3 = 1 << 8
    PREMIUM_EARLY_SUPPORTER = 1 << 9
    TEAM_PSEUDO_USER = 1 << 10
    BUG_HUNTER_LEVEL_2 = 1 << 14
    VERIFIED_BOT = 1 << 16
    VERIFIED_DEVELOPER = 1 << 17
    CERTIFIED_MODERATOR = 1 << 18
    BOT_HTTP_INTERACTIONS = 1 << 19
    SPAMMER = 1 << 20
    ACTIVE_DEVELOPER = 1 << 22
    PROVISIONAL_ACCOUNT = 1 << 23
    QUARANTINED = 1 << 44
    COLLABORATOR = 1 << 50
    RESTRICTED_COLLABORATOR = 1 << 51


class PremiumType(int, Enum):
    NONE = 0
    CLASSIC = 1
    DEFAULT = 2
    BASIC = 3


class User(Struct):
    id: int
    username: str
    discriminator: int | None = msgspec.field(default=None)
    global_name: str | None = None
    avatar: str | None = None
    banner: str | None = None
    locale: str | None = None
    flags: UserFlag = UserFlag.NONE
    public_flags: UserFlag = UserFlag.NONE
    premium_type: PremiumType = PremiumType.NONE
