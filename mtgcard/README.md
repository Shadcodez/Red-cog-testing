# MTGCard for Red 3.5+

Unofficial Magic-style card studio. Drop this folder on a Red path (`[p]addpath` / Downloader) and `[p]load mtgcard`.

Fan-made only. Not affiliated with Wizards of the Coast.

## Why v4 exists

The 3.1 cog failed often and looked unfinished because:

- Frame PNGs were **different sizes** (265×370 vs 500×698) but text/art were hardcoded for 488×680
- Art was pasted at the wrong window, then saved as JPEG
- Templates downloaded at runtime with blocking `urllib`, so a GitHub hiccup meant a blank frame
- Sessions depended on a fragile `on_message` listener
- Mana costs were raw `{3}{W}{W}` text in Arial

v4 fixes that stack.

## What you get

- **750×1050 PNG** (2.5×3.5" at 300 DPI)
- Painted frames: white, blue, black, red, green, gold, artifact, land
- Original scan templates kept, with **automatic art-window detection**
- Real Scryfall mana symbols on the card (`{W}{U}{B}{R}{G}{T}` and generics)
- Flavor text, rarity stamp, P/T box, legendary crown when the type line says Legendary
- Hybrid `[p]mtgcard` + slash command
- Works even if nobody uploads art (procedural plate)

## Commands

```
[p]mtgcard              open the tap-first studio
[p]mtgcard create       attach a picture to use it as art
[p]mtgcard make "Serra Angel" 3WW "Legendary Creature — Angel" 4/4 white text:Flying, vigilance
[p]mtgcard reset
[p]mtgcard info
```

Kind, mana, and frame are menus. The only typing is **Name & text**. Mana on the printed card uses real symbols, including `{T}` in rules.

## Install

Requires Red 3.5+ (discord.py 2) and Pillow. `aiohttp` already ships with Red.
