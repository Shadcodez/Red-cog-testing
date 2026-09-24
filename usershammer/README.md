# UsersHammer

A Red Discord Bot cog for **playful mock-moderation**. Regular members can "ban", "kick", "mute", or "timeout" each other in name only. The bot replies with typical staff lines. **No real punishments are ever applied.**

This is written to stay on the right side of Red community standards:

- It does not ban, kick, mute, timeout, delete messages, or change roles.
- Top-level commands are **banish / remove / silence / chatmute**, not `ban`, `kick`, `mute`, or `timeout`, so Red's real Mod and Mutes cogs keep working.
- User-supplied reasons cannot ping `@everyone` or roles.
- Staff can turn on role hierarchy if joke actions should follow rank.
- Staff can send matching fake cases to a joke modlog channel. That channel is not Red's real modlog.
- Settings live in Red Config only. No extra files, no outside services.

## Install

### Local path (this folder)

1. Copy this repo onto the machine that runs Red.
2. In Discord:

```
[p]addpath /full/path/to/the/folder/that/contains/usershammer
[p]load usershammer
```

The path you add is the **parent** of the `usershammer` package folder.

### From a git repo (Downloader)

```
[p]repo add usershammer <your-git-url>
[p]cog install usershammer usershammer
[p]load usershammer
```

If the cog was already loaded, use `[p]reload usershammer`.

## Member commands

| Command | Joke for |
| --- | --- |
| `[p]banish @user [reason]` | Ban |
| `[p]remove @user [reason]` | Kick |
| `[p]silence @user [reason]` | Mute |
| `[p]chatmute @user [reason]` | Timeout |
| `[p]unbanish` / `[p]unremove` / `[p]unsilence` / `[p]unchatmute` | Lift the joke |

Same actions also live under a group that *can* use the real words, because they are subcommands and do not replace core commands:

```
[p]uh ban @user being loud
[p]uh kick @user
[p]uh mute @user
[p]uh timeout @user
[p]uh actions
```

## Staff commands

Mods or anyone with Manage Server:

```
[p]uhset settings
[p]uhset toggle
[p]uhset random
[p]uhset defaults
[p]uhset disclaimer
[p]uhset embeds
[p]uhset hierarchy
[p]uhset selftarget
[p]uhset bottarget
[p]uhset cooldown 15
[p]uhset backfire
[p]uhset modlog
[p]uhset modlog channel #joke-modlog
[p]uhset modlog toggle
[p]uhset label ban Hammer
[p]uhset response add ban {target} has been banned from {server}. Reason: {reason}
[p]uhset response list ban
[p]uhset response remove ban 1
[p]uhset response clear ban
[p]uhset alias add ban hammer
[p]uhset alias list
[p]uhset alias remove ban hammer
```

You cannot register `ban`, `kick`, `mute`, `timeout`, or other reserved staff commands as aliases.

### Fake modlog

`[p]uhset modlog channel #channel` stores the channel and turns posting on. Each joke action then gets a case-style embed there (`Case #12 | Ban`, user, moderator, reason). It never creates a Red modlog case and never applies a punishment.

### Backfire

`[p]uhset backfire` turns on a **1 in 5** chance that the joke hits the member who typed the command instead of the named target.

## Response placeholders

`{target}` `{target.mention}` `{target.id}` `{target.name}`
`{moderator}` `{moderator.mention}` `{reason}`
`{action}` `{action_past}` `{server}` `{case}`

## Why the default words are banish / remove / silence / chatmute

Red already ships real `[p]ban`, `[p]kick`, `[p]mute`, and timeout tools. A third-party cog that claims those names can break core cogs or confuse staff. UsersHammer keeps the joke commands on nearby words and lets staff add extra words per server.
