# Battleship

**Author:** SHADOW

Channel battleship for Red. One game per channel, one edited message. Text chart by default. Image chart is optional.

The public board is fog of war: hits, misses, and sunk hulls only. **My fleet** opens a private chart with your ships and your tracking grid.

## Install

Add this folder's parent as a Downloader repo path, or copy `battleship` into a cog path.

```
[p]addpath <parent of this folder>
[p]load battleship
```

Pillow is required for image charts. The bot needs Embed Links, and Attach Files if image mode is on.

## Use

```
[p]battleship bot [easy|normal|hard]
[p]battleship challenge @member
[p]battleship surrender
[p]battleship mode text
[p]battleship mode image
[p]battleship ping true
```

The same commands exist as `/battleship` after the tree is synced.

Fleets are pre-rolled in DMs only. Before lock-in, pick a ship and Place it on a cell, Rotate it, or nudge it North, South, East, or West. Reroll deals a new fleet. There is no channel setup if DMs are closed. **Lock pre-rolled fleet** skips rearranging. The challenger, or the human against Cog-800, fires first.

Fire with the column and row menus, or **Type coordinate** (`B7`). **Surrender** (or `[p]battleship surrender`) gives the match to the other side. A sunk fleet or 45 minutes idle also clears the session.

## Cog-800

- easy: random shots
- normal: hunt and target, checkerboard search
- hard: ship-density chart, then finish the wounded hull
