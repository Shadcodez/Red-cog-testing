"""Pure campaign engine. No Discord imports, so it can be tested cold."""

from __future__ import annotations

import copy
import random
import string
from typing import Any


class StoryError(Exception):
    """A node, choice, or save is unusable. Never raised for ordinary play."""


def fresh_state() -> dict[str, Any]:
    return {
        "node": "crossroads",
        "flags": {},
        "items": {
            "steel sword": 1,
            "silver sword": 1,
            "swallow": 2,
            "crowns": 40,
        },
        "log": ["The road starts at White Orchard."],
        "seen": [],
        "romance_queue": None,
        "last_rest": "crossroads",
        "deaths": 0,
    }


def snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(state)


def new_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    body = "".join(random.choice(alphabet) for _ in range(6))
    return f"WH-{body[:3]}-{body[3:]}"


class Campaign:
    def __init__(self, nodes: dict[str, dict[str, Any]]):
        if "crossroads" not in nodes:
            raise StoryError("Campaign is missing the crossroads start node.")
        self.nodes = nodes
        self.problems = self.validate()

    def validate(self) -> list[str]:
        problems: list[str] = []
        for node_id, node in self.nodes.items():
            if not node.get("text"):
                problems.append(f"{node_id}: empty text")
            if not node.get("title"):
                problems.append(f"{node_id}: empty title")
            for index, choice in enumerate(node.get("choices") or []):
                nxt = choice.get("next")
                if not nxt or nxt not in self.nodes:
                    problems.append(f"{node_id} choice {index} -> missing {nxt!r}")
                if not choice.get("label"):
                    problems.append(f"{node_id} choice {index}: empty label")
            if node.get("ending") and node.get("choices"):
                problems.append(f"{node_id}: ending nodes should not offer choices")
        return problems

    def get(self, node_id: str) -> dict[str, Any]:
        node = self.nodes.get(node_id)
        if node is None:
            raise StoryError(f"Unknown place: {node_id}")
        return node

    def visible_choices(self, state: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
        node = self.get(state["node"])
        flags = state.get("flags") or {}
        items = state.get("items") or {}
        visible: list[tuple[int, dict[str, Any]]] = []
        for index, choice in enumerate(node.get("choices") or []):
            if not self._reqs_met(choice.get("requires") or {}, flags, items):
                continue
            if self._reqs_met(choice.get("hides") or {}, flags, items) and choice.get("hides"):
                continue
            visible.append((index, choice))
        return visible

    @staticmethod
    def _reqs_met(reqs: dict[str, Any], flags: dict[str, Any], items: dict[str, Any]) -> bool:
        for key, expected in reqs.items():
            if key.startswith("item:"):
                name = key.split(":", 1)[1]
                have = int(items.get(name, 0) or 0)
                if have < int(expected):
                    return False
                continue
            if key.startswith("not:"):
                name = key.split(":", 1)[1]
                if bool(flags.get(name)) == bool(expected):
                    return False
                continue
            if bool(flags.get(key)) != bool(expected):
                return False
        return True

    def apply(self, state: dict[str, Any], visible_index: int) -> dict[str, Any]:
        """Move state forward. Returns a result dict. Does not mutate on bad input."""
        choices = self.visible_choices(state)
        if visible_index < 1 or visible_index > len(choices):
            return {"ok": False, "error": "That is not one of the roads in front of you."}
        _raw_index, choice = choices[visible_index - 1]
        nxt = choice["next"]
        if nxt not in self.nodes:
            return {"ok": False, "error": "That path was never written. Stay where you are."}

        flags = dict(state.get("flags") or {})
        items = dict(state.get("items") or {})
        log = list(state.get("log") or [])
        seen = list(state.get("seen") or [])

        for key, value in (choice.get("set") or {}).items():
            flags[key] = value
        for name, delta in (choice.get("items") or {}).items():
            items[name] = int(items.get(name, 0) or 0) + int(delta)
            if items[name] <= 0:
                items.pop(name, None)
        note = choice.get("log")
        if note:
            log.append(note)
            log = log[-40:]

        node = self.nodes[nxt]
        for key, value in (node.get("set") or {}).items():
            flags[key] = value
        for name, delta in (node.get("items") or {}).items():
            items[name] = int(items.get(name, 0) or 0) + int(delta)
            if items[name] <= 0:
                items.pop(name, None)
        if node.get("log"):
            log.append(node["log"])
            log = log[-40:]
        if nxt not in seen:
            seen.append(nxt)
            seen = seen[-200:]

        romance_queue = nxt if node.get("romance") else None
        last_rest = nxt if node.get("rest") else state.get("last_rest") or "crossroads"

        state["node"] = nxt
        state["flags"] = flags
        state["items"] = items
        state["log"] = log
        state["seen"] = seen
        state["romance_queue"] = romance_queue
        state["last_rest"] = last_rest
        return {
            "ok": True,
            "node": node,
            "romance": bool(node.get("romance")),
            "ending": bool(node.get("ending")),
            "rest": bool(node.get("rest")),
        }

    def jump_rest(self, state: dict[str, Any]) -> None:
        rest = state.get("last_rest") or "crossroads"
        if rest not in self.nodes:
            rest = "crossroads"
        state["node"] = rest
        state["romance_queue"] = None

    def travel(self, state: dict[str, Any], node_id: str) -> str | None:
        node = self.nodes.get(node_id)
        if not node or not node.get("hub"):
            return "You cannot ride straight there."
        need = node.get("unlock") or {}
        if not self._reqs_met(need, state.get("flags") or {}, state.get("items") or {}):
            return "That road is still closed."
        state["node"] = node_id
        state["romance_queue"] = None
        if node.get("rest"):
            state["last_rest"] = node_id
        return None

    def open_hubs(self, state: dict[str, Any]) -> list[tuple[str, str]]:
        flags = state.get("flags") or {}
        items = state.get("items") or {}
        found = []
        for node_id, node in self.nodes.items():
            if not node.get("hub"):
                continue
            if self._reqs_met(node.get("unlock") or {}, flags, items):
                found.append((node_id, node.get("title") or node_id))
        return found
