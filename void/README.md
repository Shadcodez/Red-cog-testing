# VoidCogs

Red Discord Bot cogs for isolating members behind a role that cannot see the server.

## Void

Void is a moderation cog in the same family as core Mutes. A moderator voids a member; the cog:

1. Creates (or reuses) a configurable **void** role
2. Denies `view_channel` / `connect` (and related perms) for that role on every text, voice, stage, forum, category, and other guild channel
3. Strips every assignable role (not @everyone, not managed/boost/integration roles Discord forbids removing) and caches role IDs + names in Red Config's JSON store
4. Applies the void role so they can no longer see the server
5. Optionally expires after a duration and restores the cached roles that still exist
6. Offers the invoking staff member a **private DM** (30s timeout) asking whether to send the punished user an explanation; **Yes** opens a modal popup
7. Writes `void` / `unvoid` cases through Red's existing modlog

### Permissions

The bot needs **Manage Roles**, **Manage Channels**, and **Manage Messages** (for Nullvoid cleanup). Put the bot's highest role above the Void role.

Members with Discord's Administrator permission bypass channel overwrites. Void still strips assignable roles when the bot can manage them; the server owner cannot be voided.

Managed roles (boosts, integrations, bots) cannot be removed by Discord and are left in place.

### Install (Downloader)

```
[p]repo add VoidCogs <your-git-url>
[p]cog install VoidCogs void
[p]load void
[p]voidset setup
```

### Install (local)

```
[p]addpath /path/to/VoidCogs
[p]load void
[p]voidset setup
```

`VoidCogs` is the parent folder that contains the `void` package.

### Commands

| Command | Who | What |
| --- | --- | --- |
| `[p]void <member> [duration] [reason]` | Mod | Isolate a member. Duration examples: `30m`, `2h`, `1d`, `1w2d`. |
| `[p]unvoid <member> [reason]` | Mod | Remove Void and restore cached roles. |
| `[p]activevoids` | Mod | List current Voids. |
| `[p]voidset setup` | Admin | Create the role and apply channel overwrites. |
| `[p]voidset rolename <name>` | Admin | Rename the Void role. |
| `[p]voidset role <role>` | Admin | Use an existing role. |
| `[p]voidset applyoverwrites` | Admin | Refresh overwrites on every channel. |
| `[p]voidset defaulttime [duration]` | Admin | Default length when `[p]void` has no time. Clear by omitting duration. |
| `[p]voidset hierarchy [true/false]` | Admin | Respect role hierarchy (default on). |
| `[p]voidset settings` | Admin | Show this server's Void config. |
| `[p]nullvoid <member> [reason]` | Mod | Announce a black hole, purge recent messages, then Void (90 days default). |
| `[p]nullvoidset` | Admin | Button menu to edit Nullvoid text, media, purge cap/scope, and duration. |

Modlog case types: `void`, `unvoid`. Toggle them with `[p]modlogset cases`.

### Nullvoid

`[p]nullvoid @user` posts **Generating black hole..** and the bundled GIF (`void/data/blackhole.gif`), deletes up to 1000 of that member's messages from the last 24 hours across every channel the bot can moderate, then runs a normal Void for 90 days (roles cached and later restored by `[p]unvoid`).

`[p]nullvoidset` opens a button menu:

- Announcement text
- Media URL (or Reset bundled GIF)
- Message cap
- Lookback window (Discord bulk-delete max is 14 days)
- Toggle scope: every channel vs the command channel
- Punishment duration
- Toggle self-clean (default on) and delay (default 10 seconds). Deletes the GIF post, result embed, and command message. Modlog is kept.

### Data

Cached role IDs and names, expiry time, moderator ID, and optional reason are stored in Red Config (JSON-backed) for voided members. `[p]unvoid` writes the cached roles back. `[p]mydata forgetme` and `red_delete_data_for_user` clear that user's records. This package also ships a bundled GIF used only for Nullvoid.

### Notes

- New channels get the Void overwrite automatically.
- Void is sticky. Leaving and rejoining does not end it. The role is re-applied on join (with extra passes so autorole cogs lose) until the timer ends or a mod runs `[p]unvoid`.
- Extra roles added while voided are stripped again (managed / @everyone kept).
- If the staff member's DMs are closed, the explanation prompt is skipped on prefix commands. Slash/`[p]void` as a hybrid command can still show an ephemeral prompt when the interaction exists.
