def _(untranslated: str) -> str:  # `redgettext` will find these strings.
    return untranslated


# Discord ban delete_message_days limit.
DELETE_MESSAGE_DAYS_LIMIT = 7

# How long the sanction menu / follow-up prompts live with no interaction.
MENU_TIMEOUT_SECONDS = 150  # 2.5 minutes
# After a completed sanction, delete the menu this many seconds later.
POST_ACTION_CLEANUP_SECONDS = 10
# Action GIFs are posted before the sanction and removed this many seconds after it finishes.
GIF_CLEANUP_SECONDS = 15

# Kick-purge rate-limit knobs.
PURGE_HISTORY_LIMIT_PER_CHANNEL = 200
PURGE_CHANNEL_PAUSE = 0.8
PURGE_BATCH_PAUSE = 1.5
PURGE_MAX_CHANNELS = 40


ACTIONS_DICT: dict[str, dict[str, object]] = {
    "userinfo": {
        "label": "UserInfo",
        "emoji": "ℹ️",
        "cog_required": "Mod",
        "command": "userinfo {member.id}",
        "warn_system_command": None,
        "duration_ask_message": None,
        "reason_ask_message": None,
        "confirmation_ask_message": None,
        "finish_message": _("Here is my information about {member.display_name} ({member.id})."),
        "ask_delete_days": False,
        "void_command": False,
    },
    "warn": {
        "label": "Warn",
        "emoji": "⚠️",
        "cog_required": "Warnings",
        "command": "warn {member.id} {reason}",
        "warn_system_command": "warn 1 {member.id} {reason}",
        "duration_ask_message": None,
        "reason_ask_message": _(
            "Why do you want to warn {member.display_name} ({member.id})? (Type `cancel` to cancel or `not` for none.)",
        ),
        "confirmation_ask_message": None,
        "finish_message": _(
            "The member {member.display_name} ({member.id}) has received a warning.",
        ),
        "ask_delete_days": False,
        "void_command": False,
    },
    "ban": {
        "label": "Ban",
        "emoji": "🔨",
        "cog_required": "Mod",
        "command": "ban {member.id} {days} {reason}",
        "warn_system_command": "warn 5 {member.id} {reason}",
        "duration_ask_message": None,
        "reason_ask_message": _(
            "Why do you want to ban {member.display_name} ({member.id})? (Type `cancel` to cancel or `not` for none.)",
        ),
        "confirmation_ask_message": _(
            "Do you really want to ban {member.display_name} ({member.id}) and delete {days} day(s) of messages?",
        ),
        "finish_message": _(
            "The member {member.display_name} ({member.id}) has been banned. Messages deleted: {days} day(s).",
        ),
        "ask_delete_days": True,
        "void_command": False,
    },
    "softban": {
        "label": "SoftBan",
        "emoji": "🔂",
        "cog_required": "Mod",
        "command": "softban {member.id} {reason}",
        "warn_system_command": "warn 4 {member.id} {reason}",
        "duration_ask_message": None,
        "reason_ask_message": _(
            "Why do you want to softban {member.display_name} ({member.id})? (Type `cancel` to cancel or `not` for none.)",
        ),
        "confirmation_ask_message": _(
            "Do you really want to softban {member.display_name} ({member.id}) and clean {days} day(s) of messages?",
        ),
        "finish_message": _(
            "The member {member.display_name} ({member.id}) has been softbanned. Messages cleaned: {days} day(s).",
        ),
        "ask_delete_days": False,
        "void_command": False,
        "purge_before": True,
    },
    "tempban": {
        "label": "TempBan",
        "emoji": "💨",
        "cog_required": "Mod",
        "command": "tempban {member.id} {duration} {days} {reason}",
        "warn_system_command": "warn 5 {member.id} {duration} {reason}",
        "duration_ask_message": _(
            "How long do you want to tempban {member.display_name} ({member.id})? (Type `cancel` to cancel.)",
        ),
        "reason_ask_message": _(
            "Why do you want to tempban {member.display_name} ({member.id}) for {duration}? (Type `cancel` to cancel or `not` for none.)",
        ),
        "confirmation_ask_message": _(
            "Do you really want to tempban {member.display_name} ({member.id}) for {duration} and delete {days} day(s) of messages?",
        ),
        "finish_message": _(
            "The member {member.display_name} ({member.id}) has been tempbanned for {duration}. Messages deleted: {days} day(s).",
        ),
        "ask_delete_days": True,
        "void_command": False,
    },
    "kick": {
        "label": "Kick",
        "emoji": "👢",
        "cog_required": "Mod",
        "command": "kick {member.id} {reason}",
        "warn_system_command": "warn 3 {member.id} {reason}",
        "duration_ask_message": None,
        "reason_ask_message": _(
            "Why do you want to kick {member.display_name} ({member.id})? (Type `cancel` to cancel or `not` for none.)",
        ),
        "confirmation_ask_message": _(
            "Do you really want to kick {member.display_name} ({member.id}) and clean {days} day(s) of their messages?",
        ),
        "finish_message": _(
            "The member {member.display_name} ({member.id}) has been kicked. Messages cleaned: {days} day(s).",
        ),
        "ask_delete_days": True,
        "void_command": False,
        "purge_before": True,
    },
    "mute": {
        "label": "Mute",
        "emoji": "🔇",
        "cog_required": "Mutes",
        "command": "mute {member.id} {reason}",
        "warn_system_command": "warn 2 {member.id} {reason}",
        "duration_ask_message": None,
        "reason_ask_message": _(
            "Why do you want to mute {member.display_name} ({member.id})? (Type `cancel` to cancel or `not` for none.)",
        ),
        "confirmation_ask_message": _(
            "Do you really want to mute {member.display_name} ({member.id}) and clean {days} day(s) of messages?",
        ),
        "finish_message": _(
            "The member {member.display_name} ({member.id}) has been muted. Messages cleaned: {days} day(s).",
        ),
        "ask_delete_days": False,
        "void_command": False,
        "purge_before": True,
    },
    "mutechannel": {
        "label": "MuteChannel",
        "emoji": "👊",
        "cog_required": "Mutes",
        "command": "mutechannel {member.id} {reason}",
        "warn_system_command": None,
        "duration_ask_message": None,
        "reason_ask_message": _(
            "Why do you want to mute {member.display_name} ({member.id}) in {channel.mention}? (Type `cancel` to cancel or `not` for none.)",
        ),
        "confirmation_ask_message": _(
            "Do you really want to mute {member.display_name} ({member.id}) in {channel.mention} and clean {days} day(s) of messages?",
        ),
        "finish_message": _(
            "The member {member.display_name} ({member.id}) has been muted in {channel.mention}. Messages cleaned: {days} day(s).",
        ),
        "ask_delete_days": False,
        "void_command": False,
        "purge_before": True,
    },
    "tempmute": {
        "label": "TempMute",
        "emoji": "⏳",
        "cog_required": "Mutes",
        "command": "mute {member.id} {duration} {reason}",
        "warn_system_command": "warn 2 {member.id} {duration} {reason}",
        "duration_ask_message": _(
            "How long do you want to tempmute {member.display_name} ({member.id})? (Type `cancel` to cancel.)",
        ),
        "reason_ask_message": _(
            "Why do you want to tempmute {member.display_name} ({member.id}) for {duration}? (Type `cancel` to cancel or `not` for none.)",
        ),
        "confirmation_ask_message": _(
            "Do you really want to tempmute {member.display_name} ({member.id}) for {duration} and clean {days} day(s) of messages?",
        ),
        "finish_message": _(
            "The member {member.display_name} ({member.id}) has been tempmuted and will be unmuted in {duration}. Messages cleaned: {days} day(s).",
        ),
        "ask_delete_days": False,
        "void_command": False,
        "purge_before": True,
    },
    "tempmutechannel": {
        "label": "TempMuteChannel",
        "emoji": "⌛",
        "cog_required": "Mutes",
        "command": "mutechannel {member.id} {duration} {reason}",
        "warn_system_command": None,
        "duration_ask_message": _(
            "How long do you want to tempmute {member.display_name} ({member.id}) in {channel.mention}? (Type `cancel` to cancel.)",
        ),
        "reason_ask_message": _(
            "Why do you want to tempmute {member.display_name} ({member.id}) in {channel.mention} for {duration}? (Type `cancel` to cancel or `not` for none.)",
        ),
        "confirmation_ask_message": _(
            "Do you really want to tempmute {member.display_name} ({member.id}) in {channel.mention} for {duration} and clean {days} day(s) of messages?",
        ),
        "finish_message": _(
            "The member {member.display_name} ({member.id}) has been tempmuted in {channel.mention} and will be unmuted in {duration}. Messages cleaned: {days} day(s).",
        ),
        "ask_delete_days": False,
        "void_command": False,
        "purge_before": True,
    },
    "void": {
        "label": "Void",
        "emoji": "🕳️",
        "cog_required": "Void",
        "command": "void {member.id} {duration_reason}",
        "warn_system_command": None,
        "duration_ask_message": _(
            "How long should the Void last for {member.display_name} ({member.id})? Type `skip` to use the Void cog default, or `cancel` to cancel.",
        ),
        "reason_ask_message": _(
            "Why do you want to void {member.display_name} ({member.id})? (Type `cancel` to cancel or `not` for none.)",
        ),
        "confirmation_ask_message": _(
            "Do you really want to run `void` on {member.display_name} ({member.id})?",
        ),
        "finish_message": _(
            "Void was invoked for {member.display_name} ({member.id}).",
        ),
        "ask_delete_days": False,
        "void_command": True,
        "fallback_command": "void {member.id} {reason}",
        "skip_gif": False,
        "use_native": False,
    },
    "nullvoid": {
        "label": "NullVoid",
        "emoji": "⬛",
        "cog_required": "Void",
        "command": "nullvoid {member.id} {reason}",
        "warn_system_command": None,
        "duration_ask_message": None,
        "reason_ask_message": _(
            "Why do you want to nullvoid {member.display_name} ({member.id})? (Type `cancel` to cancel or `not` for none.)",
        ),
        "confirmation_ask_message": _(
            "Do you really want to run `nullvoid` on {member.display_name} ({member.id})? The Void cog will post its black-hole meme, purge messages, and isolate them.",
        ),
        "finish_message": None,
        "ask_delete_days": False,
        "void_command": True,
        "fallback_command": "nullvoid {member.id}",
        "skip_gif": True,
        "use_native": True,
    },
}
