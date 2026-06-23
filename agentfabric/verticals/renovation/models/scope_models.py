"""Renovation scope models."""

from dataclasses import dataclass

from .base import SerializableModel


@dataclass(frozen=True)
class Room(SerializableModel):
    name: str
    length_ft: float
    width_ft: float
    quantity: float = 1.0
    notes: str = ""

    @property
    def area_sqft(self) -> float:
        return round(self.length_ft * self.width_ft * self.quantity, 2)


@dataclass(frozen=True)
class ScopeItem(SerializableModel):
    description: str
    category: str
    quantity: float
    unit: str
    room: str = ""
    notes: str = ""
