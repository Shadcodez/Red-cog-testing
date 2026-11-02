# VoidRooms

Automatic personal voice rooms for Red-DiscordBot.

**Author:** SHADOW6six + Grok  
**Inspired by:** AutoRoom (PhasecoreX)

## Setup
1. Load the cog.
2. `[p]voidroomsset source <source_voice_channel> <destination_category>`
3. Optional: `[p]voidroomsset mode normal|locked|private`

## Features
- Join the source channel → private room created (name = game or username).
- Modes: normal / locked / private.
- `[p]allow @user` — grant access.
- `[p]eject @user` — discreetly deny + disconnect.
- `[p]transfer @user` — pass ownership.
- Auto-delete when empty.
- Dismissable creation notice (voice chat + DM).

## Requirements
- Red ≥ 3.5
- Python ≥ 3.10.9
- discord.py 2.7.x
- Bot needs: Manage Channels, Move Members, Manage Permissions, Connect, View Channel
