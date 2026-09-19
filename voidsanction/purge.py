from __future__ import annotations

import asyncio
from datetime import timedelta

import discord

from .constants import (
    DELETE_MESSAGE_DAYS_LIMIT,
    PURGE_BATCH_PAUSE,
    PURGE_CHANNEL_PAUSE,
    PURGE_HISTORY_LIMIT_PER_CHANNEL,
    PURGE_MAX_CHANNELS,
)


def clamp_delete_days(value: int | None) -> int:
    if value is None:
        return 0
    return max(0, min(int(value), DELETE_MESSAGE_DAYS_LIMIT))


def _purgeable_channels(guild: discord.Guild, me: discord.Member) -> list[discord.abc.Messageable]:
    channels: list[discord.abc.Messageable] = []
    for channel in guild.text_channels + guild.voice_channels + list(guild.threads):
        perms = channel.permissions_for(me)
        if perms.manage_messages and perms.read_message_history and perms.view_channel:
            channels.append(channel)
        if len(channels) >= PURGE_MAX_CHANNELS:
            break
    return channels


async def purge_member_messages(
    *,
    guild: discord.Guild,
    member: discord.abc.User,
    days: int,
    reason: str | None = None,
) -> tuple[int, int]:
    """
    Delete a member's recent messages across visible channels.

    Discord bulk-delete only works on messages younger than 14 days. Ban-style
    cleanup is capped at 7 days. This helper is used for kicks (the kick API
    cannot delete messages itself).

    Returns (deleted_count, channels_scanned).
    """
    days = clamp_delete_days(days)
    if days <= 0:
        return 0, 0

    me = guild.me
    if me is None:
        return 0, 0

    cutoff = discord.utils.utcnow() - timedelta(days=days)
    channels = _purgeable_channels(guild, me)
    deleted_total = 0
    scanned = 0

    for channel in channels:
        scanned += 1
        to_delete: list[discord.Message] = []
        try:
            async for message in channel.history(limit=PURGE_HISTORY_LIMIT_PER_CHANNEL, after=cutoff):
                if message.author.id == member.id and not message.pinned:
                    to_delete.append(message)
        except (discord.Forbidden, discord.HTTPException):
            await asyncio.sleep(PURGE_CHANNEL_PAUSE)
            continue

        while to_delete:
            batch = to_delete[:100]
            to_delete = to_delete[100:]
            try:
                if len(batch) == 1:
                    await batch[0].delete(reason=reason)
                    deleted_total += 1
                else:
                    await channel.delete_messages(batch, reason=reason)
                    deleted_total += len(batch)
            except discord.HTTPException:
                # Fall back to one-by-one for messages Discord refuses to bulk-delete.
                for message in batch:
                    try:
                        await message.delete(reason=reason)
                        deleted_total += 1
                    except discord.HTTPException:
                        pass
                    await asyncio.sleep(0.35)
            if to_delete:
                await asyncio.sleep(PURGE_BATCH_PAUSE)

        await asyncio.sleep(PURGE_CHANNEL_PAUSE)

    return deleted_total, scanned
