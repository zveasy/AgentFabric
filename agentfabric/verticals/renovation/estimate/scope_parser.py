"""Deterministic renovation scope parser."""

from __future__ import annotations

from agentfabric.verticals.renovation.models import Room, ScopeItem


CATEGORY_KEYWORDS = {
    "cabinet": "cabinetry",
    "floor": "flooring",
    "paint": "painting",
    "drywall": "drywall",
    "tile": "tile",
    "fixture": "fixtures",
    "demo": "demolition",
}


class ScopeParser:
    def parse(
        self,
        description: str,
        rooms: tuple[Room, ...] = (),
        quantities: dict[str, float] | None = None,
        notes: str = "",
    ) -> tuple[ScopeItem, ...]:
        if not description.strip():
            raise ValueError("scope description is required")
        quantities = quantities or {}
        room_lookup = {room.name.strip().lower(): room for room in rooms}
        items: list[ScopeItem] = []
        for raw_line in description.splitlines():
            line = " ".join(raw_line.strip().split())
            if not line:
                continue
            lowered = line.lower()
            category = next(
                (value for keyword, value in CATEGORY_KEYWORDS.items() if keyword in lowered),
                "general",
            )
            matched_room = next((room for name, room in room_lookup.items() if name in lowered), None)
            default_quantity = matched_room.area_sqft if matched_room and category in {"flooring", "painting", "tile", "drywall"} else 1.0
            quantity = float(quantities.get(line, quantities.get(category, default_quantity)))
            if quantity <= 0:
                raise ValueError("scope quantities must be positive")
            unit = "sqft" if category in {"flooring", "painting", "tile", "drywall"} else "item"
            items.append(
                ScopeItem(
                    description=line,
                    category=category,
                    quantity=round(quantity, 2),
                    unit=unit,
                    room=matched_room.name if matched_room else "",
                    notes=notes.strip(),
                )
            )
        if not items:
            raise ValueError("scope description produced no work items")
        return tuple(items)
