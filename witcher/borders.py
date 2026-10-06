"""Text frames. Kept tiny on purpose: no images, no network, no Discord objects."""

from __future__ import annotations

BANNERS = {
    "orchard": "  ∿  white orchard  ∿",
    "velen": "  †  no-man's land  †",
    "novigrad": "  ◆  free city  ◆",
    "skellige": "  ≈  the isles  ≈",
    "morhen": "  ▲  keep of the wolf  ▲",
    "stone": "  ◇  hearts of stone  ◇",
    "wine": "  ✦  toussaint  ✦",
    "romance": "  ♡  a closed door  ♡",
    "ending": "  —  the road's end  —",
    "inn": "  ⌂  fire and bad ale  ⌂",
}


def frame(title: str, body: str, banner: str = "inn", footer: str = "") -> str:
    art = BANNERS.get(banner, BANNERS["inn"])
    clean = (body or "").strip()
    if len(clean) > 3500:
        clean = clean[:3490].rstrip() + "…"
    lines = [
        "```",
        "┌──────────────────────────────────────┐",
        f"│{art.center(38)}│",
        "├──────────────────────────────────────┤",
        "```",
        f"**{title}**",
        clean,
    ]
    if footer:
        lines.append(f"_{footer}_")
    return "\n".join(lines)


def choice_block(choices: list[tuple[int, dict]]) -> str:
    if not choices:
        return "_No roads left from here._"
    rows = []
    for shown, (_raw, choice) in enumerate(choices, start=1):
        mark = "♡" if choice.get("romance") else "›"
        rows.append(f"`{shown}` {mark} {choice['label']}")
    return "\n".join(rows)
