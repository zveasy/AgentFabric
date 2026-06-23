"""Customer and project models."""

from dataclasses import dataclass

from .base import SerializableModel


@dataclass(frozen=True)
class Customer(SerializableModel):
    customer_id: str
    name: str
    email: str = ""
    phone: str = ""
    address: str = ""


@dataclass(frozen=True)
class Project(SerializableModel):
    project_id: str
    title: str
    property_address: str
    notes: str = ""
