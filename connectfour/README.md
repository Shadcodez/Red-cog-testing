# Connect Four

**Author:** SHADOW

Channel Connect Four for Red. One game per channel, one edited message. Text board by default. Image board is optional.

Red drops first. Seven column buttons. A full column goes dark. Four in a row, any direction, wins. A filled board is a draw.

## Install

The cog is already in this repo. Downloader will not see a new folder until the repo is updated. `cog install` also needs the repo name, not just the cog name.

```
[p]load downloader
[p]repo add testing https://github.com/Shadcodez/Red-cog-testing
[p]repo update testing
[p]cog install testing connectfour
[p]load connectfour
```

Use the name you already gave the repo if it is not `testing`. Pillow is installed by Downloader. The bot needs Embed Links, and Attach Files if image mode is on. Text mode works without Attach Files.

## Use

```
[p]connectfour bot [easy|normal|hard] [red|yellow|random]
[p]c4 bot
[p]connectfour challenge @member
[p]connectfour surrender
[p]connectfour mode text
[p]connectfour mode image
[p]connectfour ping true
```

The same commands exist as `/connectfour` after the tree is synced. A live game can switch board style with the Board style button. Surrender, four in a row, a draw, or 45 minutes idle wipes the session.

Red is the first disc. Against Cog-800, `yellow` makes the bot open.

## Cog-800

- easy: random column, sometimes takes a win it sees
- normal: take the win, block the threat, prefer the center, refuse a drop that loses at once
- hard: five-ply search, center first, then finish the line
