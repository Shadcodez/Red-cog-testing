# EmojiPortal Cog for Red Discord Bot

Modern, community-standard emoji management cog.  
Author: shadow

## Installation

1. Place the `emojiportal` folder in one of your Red cog paths.
2. `[p]addpath /path/to/parent` (if not already)
3. `[p]load emojiportal`

Or package it into a repo for Downloader.

## Commands

- `[p]emojiportal list` — Post all server emojis in yellow embeds, even number (8) per row, as few messages as possible.  
  **Anyone** can use (10 public uses/day/server).
- `[p]emojiportal download` — Download all emojis as 1–5 zip files (each < 50 MB). Temporary in-memory only.  
  **Anyone** can use (counts toward the same 10/day/server limit).
- `[p]emojiportal move <target_guild_id>` — Move all emojis to another server. Slow, rate-limit safe, progress saved, resumable. **Staff only**.
- `[p]emojiportal resume <job_id>` — Resume an interrupted move. **Staff only**.
- `[p]emojiportal status` — Show transfer job statuses.
- `[p]emojiportal search <query>` — Search emojis by name.
- `[p]emojiportal steal <emoji>` — Steal a single emoji into the current server. **Staff only**.
- `[p]emojiportal stats` — Emoji statistics.

## Requirements

- Bot needs **Manage Expressions** (manage_emojis) in source and target servers for move/create.
- aiohttp (included with discord.py / Red).

## Notes

- Public list + download share a simple daily limit of 10 uses per server (UTC day, stored in Config — very lightweight).
- Move process sleeps ~2.5s between creations + handles 429s with full retry_after.
- Progress is saved after every emoji so it can resume after crashes/hangups.
- Download uses only BytesIO — nothing permanently written to the bot’s disk.
- Listing respects Discord embed limits and packs densely.
- Author set to **shadow** (and will be for future cogs).

## Suggested Additional Features (for future expansion)

- Bulk delete / prune unused emojis
- Rename individual or bulk
- Role-restricted emoji listing
- Compare emoji sets between two servers
- Auto-backup on a schedule (using Red’s Scheduler or tasks)
- Reaction-based usage tracking to find unused emojis
- Import from zip
- Context menu / slash command versions
- Slot-aware move (stop early if target is full)
- WebP preference for smaller downloads
