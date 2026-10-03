# Battleship

**Author:** SHADOW

Channel battleship for Red. One game per channel, one edited image.

The public board is fog of war: hits, misses, and sunk hulls only. **My fleet** opens a private chart with your ships and your tracking grid.

## Install

The cog is already in this repo. Downloader will not see a new folder until the repo is updated. `cog install` also needs the repo name, not just the cog name.

```
[p]load downloader
[p]repo add testing https://github.com/Shadcodez/Red-cog-testing
[p]repo update testing
[p]cog install testing battleship
[p]load battleship
```

Use the name you already gave the repo if it is not `testing`. Pillow is installed by Downloader. The bot needs Embed Links and Attach Files.

## Use

```
[p]battleship bot [easy|normal|hard]
[p]battleship challenge @member
[p]battleship surrender
[p]battleship ping true
```

The same commands exist as `/battleship` after the tree is synced.

Fleets are pre-rolled in DMs only. Before lock-in, pick a ship and Place it on a cell, Rotate it, or nudge it North, South, East, or West. Reroll deals a new fleet. There is no channel setup if DMs are closed. **Lock pre-rolled fleet** skips rearranging. The challenger, or the human against Cog-800, fires first.

Fire with the column and row menus, or **Type coordinate** (`B7`). **Surrender** (or `[p]battleship surrender`) gives the match to the other side. A sunk fleet or 45 minutes idle also clears the session.

## Cog-800

- easy: random shots
- normal: hunt and target, checkerboard search
- hard: ship-density chart, then finish the wounded hull
