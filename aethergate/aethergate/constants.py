"""Signal map, presets, and visual language for AetherGate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


ACCENT = 0x00F5D4
ACCENT_WARN = 0xFF4D6D
ACCENT_OK = 0x7CFFB2
ACCENT_DIM = 0x6B7C99

# Discord audit-log reason prefix
AUDIT_PREFIX = "AetherGate"


@dataclass(frozen=True)
class Signal:
    """One permission node the lattice can write as an overwrite."""

    key: str
    attr: str
    label: str
    emoji: str
    blurb: str
    scopes: tuple  # "text", "voice", "both"


SIGNALS: Dict[str, Signal] = {
    "view": Signal(
        "view",
        "view_channel",
        "View",
        "👁",
        "See the channel (and join voice rooms).",
        ("both",),
    ),
    "speak": Signal(
        "speak",
        "send_messages",
        "Speak",
        "💬",
        "Send messages in text / announcement / forum parent.",
        ("text",),
    ),
    "embed": Signal(
        "embed",
        "embed_links",
        "Embed",
        "⧉",
        "Links auto-unfurl into rich embeds.",
        ("text",),
    ),
    "pics": Signal(
        "pics",
        "attach_files",
        "Post Pics",
        "🖼",
        "Upload images, videos, and other files.",
        ("text",),
    ),
    "history": Signal(
        "history",
        "read_message_history",
        "History",
        "📜",
        "Read messages sent before they arrived.",
        ("text",),
    ),
    "react": Signal(
        "react",
        "add_reactions",
        "React",
        "✨",
        "Add emoji reactions to messages.",
        ("text",),
    ),
    "threads": Signal(
        "threads",
        "send_messages_in_threads",
        "Threads",
        "🧵",
        "Speak inside threads.",
        ("text",),
    ),
    "connect": Signal(
        "connect",
        "connect",
        "Connect",
        "🔌",
        "Join voice and stage channels.",
        ("voice",),
    ),
    "voice": Signal(
        "voice",
        "speak",
        "Voice",
        "🎙",
        "Talk in voice channels.",
        ("voice",),
    ),
    "stream": Signal(
        "stream",
        "stream",
        "Stream",
        "📡",
        "Go live / screen-share in voice.",
        ("voice",),
    ),
}

SIGNAL_ORDER: List[str] = [
    "view",
    "speak",
    "embed",
    "pics",
    "history",
    "react",
    "threads",
    "connect",
    "voice",
    "stream",
]


# Preset templates: True allow / False deny / None inherit
PRESETS: Dict[str, Dict[str, Optional[bool]]] = {
    "observer": {
        "view": True,
        "history": True,
        "speak": False,
        "embed": False,
        "pics": False,
        "react": True,
        "threads": False,
        "connect": False,
        "voice": False,
        "stream": False,
    },
    "talker": {
        "view": True,
        "history": True,
        "speak": True,
        "embed": True,
        "pics": False,
        "react": True,
        "threads": True,
        "connect": False,
        "voice": False,
        "stream": False,
    },
    "media": {
        "view": True,
        "history": True,
        "speak": True,
        "embed": True,
        "pics": True,
        "react": True,
        "threads": True,
        "connect": False,
        "voice": False,
        "stream": False,
    },
    "voice": {
        "view": True,
        "history": None,
        "speak": False,
        "embed": False,
        "pics": False,
        "react": None,
        "threads": False,
        "connect": True,
        "voice": True,
        "stream": True,
    },
    "ghost": {
        "view": False,
        "history": False,
        "speak": False,
        "embed": False,
        "pics": False,
        "react": False,
        "threads": False,
        "connect": False,
        "voice": False,
        "stream": False,
    },
    "clear": {
        "view": None,
        "history": None,
        "speak": None,
        "embed": None,
        "pics": None,
        "react": None,
        "threads": None,
        "connect": None,
        "voice": None,
        "stream": None,
    },
}

PRESET_META = {
    "observer": ("Silent Observer", "👁", "See + history. No speaking, no media."),
    "talker": ("Talker", "💬", "Chat + embeds. No file uploads."),
    "media": ("Media Node", "🖼", "Full text: speak, embed, post pics."),
    "voice": ("Voice Node", "🎙", "Connect, speak, stream. Mute text."),
    "ghost": ("Ghost", "🕳", "Explicit deny on every signal."),
    "clear": ("Inherit Sweep", "♻", "Wipe the overwrite. Fall back to role defaults."),
}


def state_glyph(value: Optional[bool]) -> str:
    if value is True:
        return "▲ ALLOW"
    if value is False:
        return "▼ DENY"
    return "◇ INHERIT"


def state_short(value: Optional[bool]) -> str:
    if value is True:
        return "▲"
    if value is False:
        return "▼"
    return "◇"


def empty_template() -> Dict[str, Optional[bool]]:
    return {key: None for key in SIGNAL_ORDER}
