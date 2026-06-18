from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketplaceListing:
    listing_id: str
    agent_id: str
    version: str
    owner: str
    visibility: str = "private"
    trust_score: float = 0.0
    evaluation_score: float = 0.0
