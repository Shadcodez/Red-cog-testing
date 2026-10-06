"""Original campaign prose. Quest spine only — not CDPR dialogue."""

from __future__ import annotations

from . import wine, stone, sides, romance, finale, isles, city, velen, orchard


def load_nodes() -> dict:
    nodes: dict = {}
    for chunk in (
        orchard.NODES,
        velen.NODES,
        city.NODES,
        isles.NODES,
        finale.NODES,
        stone.NODES,
        wine.NODES,
        sides.NODES,
        romance.NODES,
    ):
        overlap = set(nodes).intersection(chunk)
        if overlap:
            raise RuntimeError(f"Duplicate node ids: {sorted(overlap)}")
        nodes.update(chunk)
    return nodes
