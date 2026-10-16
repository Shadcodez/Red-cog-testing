# CleanupUI

Staff-only interactive cleanup panel for Red-DiscordBot using Discord's Components V2 **Containers**.

## Features

- Clean, modern UI built with Discord Containers (accent color, separators, text displays)
- Buttons for common cleanup actions: Messages, Bot, User, Text, Spam, Self, After, Before, Between
- Channel selector to run the cleanup in a different channel
- Toggle for deleting pinned messages
- **Slow Mode** requires a unique tool password (set by server owner/admin via `[p]setcleanuppassword` — the bot DMs them). A password field appears in the modal before Slow Mode runs.
- Modals to ask for numbers, text, user IDs, or message IDs when needed
- Respects Discord's rate limits
- Staff only (requires Manage Messages permission)

## Installation

1. Place the `cleanupui` folder in your cogs directory (or install via a repo if hosted).
2. Load the cog: `[p]load cleanupui`

Requires Red-DiscordBot 3.5.21+ (discord.py 2.6+ for Components V2 support).

## Usage

```
[p]cleanuppanel
```

(Aliases: `cleanui`, `cleanupui`)

Only members with the **Manage Messages** permission can use the panel.

The panel is ephemeral-style in practice (sent in channel but command message is deleted) and times out after 5 minutes.

## Notes

- **Normal mode**: Uses bulk delete where possible (fast, limited to messages < 14 days old).
- **Slow mode**: Deletes messages one-by-one with a ~2.5 second delay. Works on messages of any age. Automatically stops after **5 minutes** to prevent endless runs. Expect roughly 20–25 messages per minute.
- Messages older than 14 days cannot be bulk-deleted; Slow Mode is the way to clean them.
- The bot needs Manage Messages in the target channel.

Made with community standards in mind for Red cogs.
