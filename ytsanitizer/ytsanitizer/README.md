# ytsanitizer

Red-DiscordBot cog. Strips YouTube's `?si=` share identifier, retriggers the embed, and optionally deletes the original post.

`v`, `t`, `list`, and `index` are kept. Timestamps and playlists still work. `feature=share` is removed with `si`. Other sites are left alone.

Set the `author` field in both `info.json` files to your name before publishing.

## Install

From a local path:

```
[p]addpath /path/to/folder/that/contains/ytsanitizer
[p]load ytsanitizer
```

Downloader: put this folder in a cog repo next to a repo-level `info.json`, then `[p]repo add` and `[p]cog install`.

## Modes

Default is `manual`. Nothing is deleted until you turn that toggle on.

| Mode | What it does |
| --- | --- |
| `manual` | Command only. Default. |
| `auto` | Listener cleans new posts that contain a YouTube `?si=` link. |
| `off` | Listener and nothing else. The command still works. |

`[p]cog disable` in a server also stops the listener, same as any other Red cog.

## Commands

- `[p]ytsanitize <text>` — clean a pasted link. Does not delete anything.
- `[p]ytsanitize` as a reply — clean that post, then follow the delete toggle.
- `[p]ytsanitizeset` — show mode and delete toggle.
- `[p]ytsanitizeset mode <auto|manual|off>` — set the mode. Manage Server.
- `[p]ytsanitizeset delete [on|off]` — toggle, or set, deleting the original. Manage Server.

## Permissions

- Send Messages, Embed Links — retrigger
- Manage Messages — only if delete is on
- Manage Server — settings commands

In manual mode, a reply is only deleted if delete is on and the invoker wrote the post or has Manage Messages.

## Data

Guild config only: `mode`, `delete_original`. No message content or user ids. `red_delete_data_for_user` is a no-op, declared for `[p]mydata`.

User-facing strings go through Red's translator. Extract with `redgettext` if you add a locale.
