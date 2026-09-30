# EmbedUtils 3

A new embed cog for Red 3.5+, built from the PhenoM4n4n and AAA3A designs rather than sharing either cog’s Config namespace.

- Hybrid prefix + slash group
- One send path for JSON, YAML, files, URLs, and messages
- Buttons, dropdowns, and modal popups
- Message context menus
- Autocomplete on stored names
- Native webhook reuse
- Silent one-time import from Phen and AAA3A storage

No `AAA3A_utils` dependency. Requires `PyYAML`.

## Install

Put `embedutils` on a cog path:

```
[p]addpath <parent folder>
[p]load embedutils
[p]slash sync
```

Context menus appear after a slash sync.

## Everyday commands

| Command | Purpose |
| --- | --- |
| `[p]embed [channel] [color] <title> <description>` | Quick embed |
| `[p]embed builder` | Interactive editor |
| `[p]embed popup` | Modal create |
| `[p]embed dropdown` | Pick stored embeds |
| `[p]embed send <source>` | `json` `yaml` `file` `yamlfile` `url` `message` |
| `[p]embed json` / `yaml` / `fromfile` / `pastebin` / `message` | Direct sources |
| `[p]embed store <name> [source]` | Save |
| `[p]embed post <names>` | Post saved embeds |
| `[p]embed webhook <username> <names>` | Post as a webhook |
| `[p]embed list` / `info` / `unstore` / `download` / `downloadstored` | Manage |
| `[p]embed dm` / `dmme` / `event` | Extras |
| `[p]embed limits` | Owner storage caps |

Right-click a message → **Build embed** or **Download embed JSON**.

## Storage

New Config identifier. First load copies *missing* names from:

- Phen EmbedUtils (`embeds`)
- AAA3A EmbedUtils (`stored_embeds`)

Existing names in this cog are never overwritten. Guild cap and global cap default to 100 (`[p]embed limits`).

## Credits

PhenoM4n4n for the original EmbedUtils, AAA3A for the hybrid rewrite and dashboard editor page.
