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
ALL_TEMPLATE_NAMES = (*TEMPLATE_NAMES, "change_order_standard")


def load_template(template_id: str) -> dict[str, object]:
    if template_id not in ALL_TEMPLATE_NAMES:
        raise ValueError("unknown renovation proposal template")
    path = Path(__file__).with_name(f"{template_id}.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if template_id == "change_order_standard":
        required = {"template_id", "version", "style", "clauses"}
    else:
        required = {
            "template_id",
            "version",
            "style",
            "payment_terms",
            "project_phases",
            "warranty_months",
            "clauses",
        }
    if not required <= set(value):
        raise ValueError("renovation proposal template is incomplete")
    if "payment_terms" in value and sum(float(item["percentage"]) for item in value["payment_terms"]) != 100:
        raise ValueError("proposal payment terms must total 100 percent")
    return value


__all__ = ["ALL_TEMPLATE_NAMES", "TEMPLATE_NAMES", "load_template"]
