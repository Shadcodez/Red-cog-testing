# Giveaways

A modern Red-DiscordBot cog by **shad**.

Button-based giveaways. `[p]giveaway` opens a private popup form, then a
private EmbedCreator-style editor. Setup messages delete themselves.

## Install

Place the `giveaways` folder in a directory you add with `[p]addpath`, then:

```
[p]load giveaways
[p]help Giveaways
```

## Commands

| Command | Who | What |
| --- | --- | --- |
| `[p]giveaway` | Mod / Manage Messages | Private setup form + editor |
| `[p]giveaway cancel [id]` | Mod / Manage Messages | Cancel without drawing |
| `[p]giveaway end [id]` | Mod / Manage Messages | End now and draw winners |
| `[p]giveaway edit <id> ...` | Mod / Manage Messages | Change prize, time, winners, etc. |
| `[p]giveaway reroll <id> [n]` | Mod / Manage Messages | Draw new winners from the same pool |
| `[p]giveaway list` | Everyone | Active giveaways |
| `[p]giveaway info <id>` | Everyone | Embed preview of stored data |
| `[p]giveaway entries [id]` | Mod / Manage Messages | Entrant / ticket counts |
| `[p]giveaway bonus <id> <role> <n>` | Mod / Manage Messages | Extra tickets for a role |
| `[p]giveawayset` | Admin / Manage Guild | Server defaults |

Aliases: `gaway`, `gw`. Settings group: `giveawayset` / `gset`.

## Interactive builder

`[p]giveaway` is the create command. Flow:

1. The invoking message is deleted when the bot can manage messages.
2. A short **Set up / Cancel** prompt is posted (45s, then it deletes itself).
3. **Set up** opens a popup form: prize, duration, winners, description, colour.
4. After submit, the prompt is deleted and a **private** editor appears (only you see it). That editor is the EmbedCreator-style UI.
5. **Cancel** or dismissing the private message aborts at any time.

| Control | What it sets |
| --- | --- |
| Prize / Duration / Winners / Description / Colour | Core embed fields via modals |
| Appearance | Image, thumbnail, enter-button label |
| Requirements | Account age, server age, bonus tickets, host entry |
| Host entry / DM winners | Toggle buttons |
| Role menu | Required role |
| Channel menu | Where the giveaway is posted |
| Start giveaway | Posts the public giveaway |
| Cancel | Aborts; private editor is cleared |

`[p]giveaway edit <id>` with no flags opens the same menu against a live giveaway.

To skip the menu: `[p]giveaway start builder: no duration: 1h prize: Nitro`

Supported flags: `duration` (`time`, `ends`, `for`), `prize`, `winners`,
`description`, `channel`, `require`, `blacklist`, `image`, `thumbnail`,
`colour`, `allow_host`, `dm`, `builder`, `account_age`, `server_age`,
`label`, `ping`.

## Permissions

Management commands use `@commands.mod_or_permissions(manage_messages=True)`.
Settings use `@commands.admin_or_permissions(manage_guild=True)`.

That works with Red's core mod/admin roles **and** the Permissions cog:

```
[p]permissions addrule allow giveaway start @Giveaway Staff
[p]permissions addrule deny giveaway start #general
```

## Notes

- Join buttons stay active across cog reloads (`timeout=None` persistent view).
- Timers sleep in 30 second chunks so cancel / edit apply quickly.
- Ended giveaways stay stored for 7 days so you can reroll, then they are cleaned up on next load.
- `[p]mydata forgetme` removes that user's stored entries.
