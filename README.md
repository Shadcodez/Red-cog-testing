# VoidCogs

Red Discord Bot cogs for isolating members behind a role that cannot see the server.

## Void

Void is a moderation cog in the same family as core Mutes. A moderator voids a member; the cog:

1. Creates (or reuses) a configurable **void** role
2. Denies `view_channel` / `connect` (and related perms) for that role on every text, voice, stage, forum, category, and other guild channel
3. Strips the member's assignable roles and caches them in Red Config
4. Applies the void role so they can no longer see the server
5. Optionally expires after a duration and restores the cached roles
6. Offers the invoking staff member a **private DM** (30s timeout) asking whether to send the punished user an explanation; **Yes** opens a modal popup
7. Writes `void` / `unvoid` cases through Red's existing modlog

### Permissions

The bot needs **Manage Roles** and **Manage Channels**. Put the bot's highest role above the Void role.

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

Modlog case types: `void`, `unvoid`. Toggle them with `[p]modlogset cases`.

### Data

Cached role IDs, expiry time, moderator ID, and optional reason are stored in Red Config for members who are (or were, until cleaned) voided. `[p]mydata forgetme` and `red_delete_data_for_user` clear that user's records.

### Notes

- New channels get the Void overwrite automatically.
- Rejoining while still voided re-applies the role.
- Extra roles added while voided are removed again (managed / @everyone kept).
- If the staff member's DMs are closed, the explanation prompt is skipped on prefix commands. Slash/`[p]void` as a hybrid command can still show an ephemeral prompt when the interaction exists.
