# Kerrigan

Casual staff moderation assistant for Red-DiscordBot that works with VoidSanction.

Staff can ping the bot with a casual sentence containing a moderation action and a user. The bot extracts the action, target, and optional duration, asks for a reason if needed, optionally confirms the full request, then executes the action through VoidSanction.

## Features

- Parses casual messages for actions (ban, kick, mute, void, nullvoid, etc.) and targets (mention or ID)
- Supports duration if present in the sentence (e.g. 2h, 1d, 30m)
- Optional confirmation step that reads back the full request and waits for yes/no
- Soft theme toggle for slightly more flavorful (but still minimal) responses
- Automatic cleanup of the conversation messages after a configurable delay
- Fully configurable per server
- Respects staff permissions (manage_messages, Red mod/admin roles, or custom staff roles)

## Requirements

- Red-DiscordBot 3.5+
- VoidSanction cog loaded and configured
- Bot needs Manage Messages (for cleanup) and the permissions required by VoidSanction for the actions it will perform

## Installation

Place the `kerrigan` folder in a path you have added with `[p]addpath`, then:

```
[p]load kerrigan
```

Or install via downloader if you publish the repo.

## Usage

Staff member pings the bot:

```
@Bot void @user 2h for spamming
```

or

```
@Bot kick 123456789012345678 please
```

The bot will:

1. Ask for a reason if one is not clearly present
2. Read back the request and wait for yes/no (if confirmation is enabled)
3. Execute the action via VoidSanction
4. Clean up the messages after the configured delay (if enabled)

## Settings

`[p]kerriganset` — show current settings

- `[p]kerriganset toggle [true/false]` — enable/disable
- `[p]kerriganset confirm [true/false]` — require yes/no confirmation
- `[p]kerriganset theme [true/false]` — soft theme on/off
- `[p]kerriganset cleanup [true/false] [delay]` — cleanup toggle and delay in seconds
- `[p]kerriganset staffrole [role]` — add/remove/view custom staff roles

## Author

shadow
