# VoidSanction

A modern Red-DiscordBot fork of [AAA3A's SimpleSanction](https://github.com/AAA3A-AAA3A/AAA3A-cogs/tree/main/simplesanction).

The sanction menu still gathers userinfo, warn, ban, softban, tempban, kick, mute, and temp-mutes in one button view. This fork adds:

1. **Message cleanup prompt** — kick, ban, and tempban ask how many days of that user's messages to delete (0–7, Discord's limit).
2. **Void cog support** — wired to [Shadcodez Void](https://github.com/Shadcodez/Red-cog-testing/tree/main/void). **Nullvoid is left entirely to that cog** (bundled/custom black-hole GIF, purge, 90-day isolate, 10s self-clean).
3. **Self-cleaning UI** — the menu is deleted **10 seconds after an action finishes**, or after **2.5 minutes** if nobody uses it.
4. **Per-action GIF URLs** — `[p]setvoidsanction gif set <action> <url>` posts that GIF *before* the sanction, then deletes it **15 seconds after** the action completes. Nullvoid ignores this setting.

Kick cannot delete messages through Discord's kick endpoint, so VoidSanction purges recent messages itself (rate-limit aware) and then runs `[p]kick`. Ban and tempban pass the day count straight into Red's Mod cog (`ban <user> <days> <reason>`).

## Requirements

- Red 3.5+
- Python 3.10+
- Core cogs you actually want to invoke: `Mod`, `Warnings` / WarnSystem, `Mutes`
- [AAA3A_utils](https://github.com/AAA3A-AAA3A/AAA3A_utils)
- Optional: [Shadcodez Void](https://github.com/Shadcodez/Red-cog-testing/tree/main/void) for `void` / `nullvoid`

## Install

From a local path:

```
[p]addpath /path/to/parent-of-voidsanction
[p]load voidsaction
```

Or as a Downloader repo (this folder layout already has a root `info.json`):

```
[p]repo add voidsaction-cogs <your-git-url>
[p]cog install voidsaction-cogs voidsaction
[p]pipinstall git+https://github.com/AAA3A-AAA3A/AAA3A_utils.git
[p]load voidsaction
```

Do not load SimpleSanction and VoidSanction at the same time if you also want the `punishmember` / `punishuser` aliases — they collide.

## Commands

| Command | What it does |
| --- | --- |
| `[p]voidsanction [member]` | Open the button menu |
| `[p]vsanction` | Same alias |
| `[p]voidsanction ban @user` | Ban flow, then days prompt |
| `[p]voidsanction kick @user` | Kick flow, then days prompt + purge |
| `[p]voidsanction void @user` | Invoke your Void cog |
| `[p]voidsanction nullvoid @user` | Invoke your Void cog |
| `[p]setvoidsanction` | Guild settings |
| `[p]setvoidsanction gif set <action> <url>` | GIF posted before that action |
| `[p]setvoidsanction gif clear <action>` | Remove one GIF |
| `[p]setvoidsanction gif list` | Show every action URL |

Numbered shortcuts from SimpleSanction still work (`00` menu through `12` nullvoid).

There is also a user context menu named **Void Sanction**. Enable and sync it with `[p]slash enablecog VoidSanction` then `[p]slash sync`.

## Settings

```
[p]setvoidsanction askdeletedays true
[p]setvoidsanction askdeletedayssoftban false
[p]setvoidsanction askdeletedaysmute false
[p]setvoidsanction defaultdeletedays 0
[p]setvoidsanction actionconfirmation true
[p]setvoidsanction reasonrequired true
[p]setvoidsanction finishmessage true
[p]setvoidsanction showauthor true
[p]setvoidsanction usewarnsystem true
[p]setvoidsanction thumbnail <url>
```

When `askdeletedays` is off, kick/ban use `defaultdeletedays` (0–7) with no prompt.

Mute and softban message cleanup is **off by default**. Turn them on separately:

- `[p]setvoidsanction askdeletedaysmute true` — mute / mutechannel / tempmute / tempmutechannel ask 0–7 days, then purge before muting.
- `[p]setvoidsanction askdeletedayssoftban true` — softban asks 0–7 days. `1` keeps Red's native softban. `0` kicks with no purge. Other values purge then kick.

GIF URLs already work for mute and softban via `[p]setvoidsanction gif set mute <url>` and `gif set softban <url>`.

## Void / NullVoid wiring

Matches the Shadcodez Void cog:

- `void <id> [duration] [reason]` — duration can be skipped (`skip`) so Void uses `[p]voidset defaulttime`.
- `nullvoid <id> [reason]` — VoidSanction does **not** post a GIF, ask for delete-days, or purge. The Void cog already announces `Generating black hole..` with `void/data/blackhole.gif` (or `[p]nullvoidset` media URL), purges, voids for 90 days, and self-cleans after 10 seconds.

If those commands are not loaded, the buttons are hidden.

## Action GIFs

```
[p]setvoidsanction gif set ban https://example.com/ban.gif
[p]setvoidsanction gif set kick https://example.com/kick.gif
[p]setvoidsanction gif set void https://example.com/void.gif
[p]setvoidsanction gif list
[p]setvoidsanction gif clear ban
```

The GIF is sent first. After the real moderation command returns, a 15-second timer deletes that GIF message. Nullvoid never uses this list.

## Rate limits

- Ban/tempban cleanup is one Discord API field (`delete_message_days`, max 7). No extra sweeping.
- Kick cleanup walks up to 40 channels the bot can moderate, reads at most 200 messages per channel after the cutoff, bulk-deletes in batches of 100, and sleeps between batches and channels.
- The menu is deleted 10 seconds after a finished action, or immediately after 150 seconds idle.

Bulk delete cannot touch messages older than 14 days; this cog never asks for more than 7.

## Credits

Original SimpleSanction by [AAA3A](https://github.com/AAA3A-AAA3A/AAA3A-cogs), MIT licensed. This fork keeps that license and the AAA3A_utils dependency.
