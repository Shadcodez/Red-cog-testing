# AetherGate

Futuristic per-channel role access control for [Red Discord Bot](https://github.com/Cog-Creators/Red-DiscordBot) 3.5+.

AetherGate forges a named role, binds it to a **lattice**, and lets moderators paint Discord channel overwrites without digging through server settings. The holopanel is built on discord.py 2 views: selects, buttons, modals, and a channel-by-channel lab.

## What it does

- Creates a new role from a name you choose (or **adopts** an existing one).
- Stores that role as a managed node in Red `Config`.
- Lets you edit a **signal matrix** focused on the permissions people actually fight over:
  - **View** (`view_channel`)
  - **Speak** (`send_messages`)
  - **Embed** (`embed_links`)
  - **Post Pics** (`attach_files`)
  - History, React, Threads
  - Connect, Voice Speak, Stream
- Each signal is tri-state: **ALLOW / DENY / INHERIT**.
- Commits that matrix onto:
  - channels picked with a Channel Select,
  - channels typed as `#general #media #voice-lab`,
  - every text channel, or every voice channel.
- **Channel Lab** walks locked targets one node at a time and writes live.
- Presets: Silent Observer, Talker, Media Node, Voice Node, Ghost, Inherit Sweep.
- Rename, scan live overwrites, untrack, or delete with confirmation.
- Respects Discord role hierarchy (operator and bot must outrank the target).
- Never grants Administrator. Created roles start with empty guild permissions.

## Install (local)

```
[p]addpath /path/to/this/folder
[p]load aethergate
```

The path you add is the **parent** of the `aethergate/` package folder.

## Commands

Prefix below is `[p]`. Aliases: `agate`, `lattice`.

| Command | Purpose |
| --- | --- |
| `[p]agate create <name>` | Forge a new role and open the holopanel |
| `[p]agate adopt <role>` | Bind an existing role |
| `[p]agate panel <role>` | Open the interactive editor |
| `[p]agate rename <role> <name>` | Retitle the role |
| `[p]agate apply <role> #a #b #c` | Commit the stored template onto typed channels |
| `[p]agate preset <role> media #a #b` | Load a preset and optionally commit it |
| `[p]agate scan <role>` | Dump live overwrites |
| `[p]agate list` | Show bound nodes |
| `[p]agate untrack <role>` | Drop from the lattice, keep the Discord role |
| `[p]agate delete <role>` | Confirm and destroy the Discord role |
| `[p]agate signals` | Catalogue of paint-able permissions |

Required operator perms: Red admin **or** `Manage Roles` + `Manage Channels`.  
Bot perms: `Manage Roles`, `Manage Channels`, `Embed Links`.

## Holopanel

1. Select a **signal** (View, Speak, Embed, Post Pics, …).
2. Press **ALLOW**, **DENY**, or **INHERIT**.
3. Optionally load a **preset**.
4. Lock targets with the channel picker **or** **Paste #channels**.
5. **Commit Selected**, **All Text**, or **All Voice**.
6. **Channel Lab** opens an ephemeral walker for the locked targets.

Edits write real Discord permission overwrites and show up in the audit log as `AetherGate …`.

## Community notes

- Cog class and every command have docstrings.
- Data lives in Red `Config` (`force_registration=True`).
- Implements `red_delete_data_for_user` and `__red_end_user_data_statement__`.
- Hierarchy is enforced the same way Red's core Admin cog does.
- Overwrite bursts sleep every 8 channels to stay friendly with Discord rate limits.
- Logging namespace: `red.aethergate.aethergate`.

## License

MIT
