"""Pure helpers for the Giveaways cog. No Discord / Red imports."""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


MAX_WINNERS = 20
MIN_DURATION_SECONDS = 10
MAX_DURATION_SECONDS = 60 * 24 * 60 * 60  # 60 days
MAX_ACTIVE_PER_GUILD = 25
MAX_PRIZE_LEN = 256
MAX_DESCRIPTION_LEN = 2000
CLEANUP_AFTER_SECONDS = 7 * 24 * 60 * 60


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ts_now() -> float:
    return utcnow().timestamp()


def clamp_winners(value: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(MAX_WINNERS, value))


def validate_duration_seconds(seconds: float) -> Tuple[bool, str]:
    if seconds < MIN_DURATION_SECONDS:
        return False, f"Duration must be at least {MIN_DURATION_SECONDS} seconds."
    if seconds > MAX_DURATION_SECONDS:
        return False, "Duration cannot exceed 60 days."
    return True, ""


def humanize_seconds(seconds: float) -> str:
    """Short human readable duration used in builder previews."""
    seconds = int(max(0, seconds))
    weeks, rem = divmod(seconds, 7 * 24 * 3600)
    days, rem = divmod(rem, 24 * 3600)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: List[str] = []
    if weeks:
        parts.append(f"{weeks}w")
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def discord_relative(ts: float) -> str:
    return f"<t:{int(ts)}:R>"


def discord_absolute(ts: float) -> str:
    return f"<t:{int(ts)}:F>"


def tickets_for_member(
    member_role_ids: Iterable[int],
    bonus_roles: Mapping[str, int],
) -> int:
    """Base 1 ticket plus extra tickets from bonus roles (not multiplicative)."""
    tickets = 1
    role_set = {int(r) for r in member_role_ids}
    for role_id, extra in bonus_roles.items():
        try:
            rid = int(role_id)
            extra_n = int(extra)
        except (TypeError, ValueError):
            continue
        if rid in role_set and extra_n > 0:
            tickets += extra_n
    return max(1, min(tickets, 100))


def can_enter(
    *,
    user_id: int,
    is_bot: bool,
    host_id: int,
    allow_host: bool,
    member_role_ids: Iterable[int],
    required_roles: Sequence[int],
    blacklist_roles: Sequence[int],
    account_created_ts: Optional[float],
    joined_ts: Optional[float],
    min_account_days: int,
    min_server_days: int,
    now_ts: Optional[float] = None,
) -> Tuple[bool, str]:
    if is_bot:
        return False, "Bots cannot enter giveaways."
    if not allow_host and int(user_id) == int(host_id):
        return False, "The host cannot enter this giveaway."

    role_set = {int(r) for r in member_role_ids}

    if required_roles:
        needed = {int(r) for r in required_roles}
        if role_set.isdisjoint(needed):
            return False, "You are missing a required role to enter."

    if blacklist_roles:
        blocked = {int(r) for r in blacklist_roles}
        if role_set.intersection(blocked):
            return False, "One of your roles is not allowed to enter."

    now = now_ts if now_ts is not None else ts_now()
    if min_account_days and account_created_ts:
        age_days = (now - float(account_created_ts)) / 86400
        if age_days < min_account_days:
            return False, f"Your account must be at least {min_account_days} day(s) old."
    if min_server_days and joined_ts:
        stay_days = (now - float(joined_ts)) / 86400
        if stay_days < min_server_days:
            return False, f"You must have been in this server for at least {min_server_days} day(s)."
    return True, ""


def pick_winners(
    entries: Mapping[str, int],
    winners: int,
    *,
    exclude: Optional[Iterable[int]] = None,
    rng: Optional[random.Random] = None,
) -> List[int]:
    """Weighted draw without replacement of users.

    ``entries`` maps user id (str or int) -> ticket count.
    """
    rng = rng or random.Random()
    exclude_set = {int(x) for x in (exclude or [])}
    pool: List[int] = []
    weights: List[int] = []
    for raw_uid, raw_tickets in entries.items():
        try:
            uid = int(raw_uid)
            tickets = int(raw_tickets)
        except (TypeError, ValueError):
            continue
        if uid in exclude_set or tickets <= 0:
            continue
        pool.append(uid)
        weights.append(tickets)

    count = min(clamp_winners(winners), len(pool))
    chosen: List[int] = []
    for _ in range(count):
        if not pool:
            break
        pick = rng.choices(pool, weights=weights, k=1)[0]
        chosen.append(pick)
        idx = pool.index(pick)
        pool.pop(idx)
        weights.pop(idx)
    return chosen


def default_giveaway_payload(
    *,
    guild_id: int,
    channel_id: int,
    message_id: int,
    host_id: int,
    prize: str,
    end_ts: float,
    winners: int = 1,
    description: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "guild_id": int(guild_id),
        "channel_id": int(channel_id),
        "message_id": int(message_id),
        "host_id": int(host_id),
        "prize": prize[:MAX_PRIZE_LEN],
        "description": (description or "")[:MAX_DESCRIPTION_LEN],
        "winners": clamp_winners(winners),
        "end_ts": float(end_ts),
        "started_ts": ts_now(),
        "ended": False,
        "cancelled": False,
        "ended_ts": None,
        "winner_ids": [],
        "entries": {},
        "required_roles": [],
        "blacklist_roles": [],
        "bonus_roles": {},
        "min_account_days": 0,
        "min_server_days": 0,
        "allow_host": False,
        "dm_winners": True,
        "image": None,
        "thumbnail": None,
        "color": None,
        "button_label": "Enter",
        "button_emoji": "🎉",
        "ping_role": None,
    }
    if extra:
        data.update(extra)
    return data


def is_active(gw: Mapping[str, Any]) -> bool:
    return bool(gw) and not gw.get("ended") and not gw.get("cancelled")


def should_cleanup(gw: Mapping[str, Any], now: Optional[float] = None) -> bool:
    if is_active(gw):
        return False
    ended_ts = gw.get("ended_ts") or gw.get("end_ts") or 0
    now = now if now is not None else ts_now()
    try:
        return (now - float(ended_ts)) >= CLEANUP_AFTER_SECONDS
    except (TypeError, ValueError):
        return True


def apply_edit(gw: Dict[str, Any], changes: Mapping[str, Any], now_ts: Optional[float] = None) -> Dict[str, Any]:
    """Mutate a giveaway payload with validated edits. Returns the same dict."""
    if "prize" in changes and changes["prize"]:
        gw["prize"] = str(changes["prize"])[:MAX_PRIZE_LEN]
    if "description" in changes and changes["description"] is not None:
        gw["description"] = str(changes["description"])[:MAX_DESCRIPTION_LEN]
    if "winners" in changes and changes["winners"] is not None:
        gw["winners"] = clamp_winners(int(changes["winners"]))
    if "end_ts" in changes and changes["end_ts"] is not None:
        gw["end_ts"] = float(changes["end_ts"])
    if "add_seconds" in changes and changes["add_seconds"]:
        base = max(float(gw.get("end_ts") or 0), (now_ts or ts_now()))
        gw["end_ts"] = base + float(changes["add_seconds"])
    for key in (
        "required_roles",
        "blacklist_roles",
        "bonus_roles",
        "min_account_days",
        "min_server_days",
        "allow_host",
        "dm_winners",
        "image",
        "thumbnail",
        "color",
        "button_label",
        "button_emoji",
        "ping_role",
    ):
        if key in changes and changes[key] is not None:
            gw[key] = changes[key]
    return gw


def entry_count(gw: Mapping[str, Any]) -> int:
    entries = gw.get("entries") or {}
    return len(entries)


def ticket_count(gw: Mapping[str, Any]) -> int:
    entries = gw.get("entries") or {}
    total = 0
    for v in entries.values():
        try:
            total += max(0, int(v))
        except (TypeError, ValueError):
            continue
    return total
