"""Flag converters for giveaway creation and edits."""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

import discord
from redbot.core import commands
from redbot.core.commands import ColourConverter, FlagConverter, TimedeltaConverter


class GiveawayFlags(FlagConverter, case_insensitive=True):
    """Flags for ``[p]giveaway start``.

    Example
    -------
    ``[p]giveaway start duration: 12h winners: 2 prize: Nitro Classic``
    """

    duration: Optional[timedelta] = commands.flag(
        name="duration",
        aliases=["time", "ends", "for"],
        default=None,
        converter=TimedeltaConverter(
            default_unit="minutes",
            minimum=timedelta(seconds=10),
            maximum=timedelta(days=60),
        ),
    )
    prize: Optional[str] = commands.flag(name="prize", aliases=["reward"], default=None)
    winners: int = commands.flag(name="winners", aliases=["wins", "winner"], default=1)
    description: Optional[str] = commands.flag(
        name="description", aliases=["desc"], default=None
    )
    channel: Optional[discord.TextChannel] = commands.flag(
        name="channel", aliases=["chan"], default=None
    )
    require: Optional[discord.Role] = commands.flag(
        name="require", aliases=["required", "role"], default=None
    )
    blacklist: Optional[discord.Role] = commands.flag(
        name="blacklist", aliases=["deny", "block"], default=None
    )
    image: Optional[str] = commands.flag(name="image", default=None)
    thumbnail: Optional[str] = commands.flag(name="thumbnail", aliases=["thumb"], default=None)
    colour: Optional[discord.Colour] = commands.flag(
        name="colour", aliases=["color"], default=None, converter=ColourConverter
    )
    allow_host: bool = commands.flag(name="allow_host", aliases=["hostcanenter"], default=False)
    dm_winners: bool = commands.flag(name="dm", aliases=["dm_winners"], default=True)
    builder: bool = commands.flag(name="builder", aliases=["menu"], default=True)
    min_account_days: int = commands.flag(name="account_age", aliases=["min_account"], default=0)
    min_server_days: int = commands.flag(name="server_age", aliases=["min_server"], default=0)
    button_label: Optional[str] = commands.flag(name="label", aliases=["button"], default=None)
    ping: Optional[discord.Role] = commands.flag(name="ping", aliases=["pingrole"], default=None)


class GiveawayEditFlags(FlagConverter, case_insensitive=True):
    """Flags for ``[p]giveaway edit``."""

    prize: Optional[str] = commands.flag(name="prize", aliases=["reward"], default=None)
    winners: Optional[int] = commands.flag(name="winners", aliases=["wins"], default=None)
    description: Optional[str] = commands.flag(name="description", aliases=["desc"], default=None)
    add_time: Optional[timedelta] = commands.flag(
        name="add",
        aliases=["extend"],
        default=None,
        converter=TimedeltaConverter(
            default_unit="minutes",
            minimum=timedelta(seconds=10),
            maximum=timedelta(days=30),
        ),
    )
    set_time: Optional[timedelta] = commands.flag(
        name="duration",
        aliases=["time", "set"],
        default=None,
        converter=TimedeltaConverter(
            default_unit="minutes",
            minimum=timedelta(seconds=10),
            maximum=timedelta(days=60),
        ),
    )
    image: Optional[str] = commands.flag(name="image", default=None)
    thumbnail: Optional[str] = commands.flag(name="thumbnail", aliases=["thumb"], default=None)
    colour: Optional[discord.Colour] = commands.flag(
        name="colour", aliases=["color"], default=None, converter=ColourConverter
    )
    allow_host: Optional[bool] = commands.flag(name="allow_host", default=None)
    dm_winners: Optional[bool] = commands.flag(name="dm", default=None)
    button_label: Optional[str] = commands.flag(name="label", aliases=["button"], default=None)
    min_account_days: Optional[int] = commands.flag(name="account_age", default=None)
    min_server_days: Optional[int] = commands.flag(name="server_age", default=None)
