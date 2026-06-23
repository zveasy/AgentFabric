"""Versioned RenovationOS templates."""

from __future__ import annotations

import json
from pathlib import Path


TEMPLATE_NAMES = (
    "standard_proposal",
    "premium_proposal",
    "light_remodel_template",
    "full_remodel_template",
)


def load_template(template_id: str) -> dict[str, object]:
    if template_id not in TEMPLATE_NAMES:
        raise ValueError("unknown renovation proposal template")
    path = Path(__file__).with_name(f"{template_id}.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {"template_id", "version", "style", "payment_terms", "project_phases", "warranty_months", "clauses"}
    if not required <= set(value):
        raise ValueError("renovation proposal template is incomplete")
    if sum(float(item["percentage"]) for item in value["payment_terms"]) != 100:
        raise ValueError("proposal payment terms must total 100 percent")
    return value


__all__ = ["TEMPLATE_NAMES", "load_template"]
