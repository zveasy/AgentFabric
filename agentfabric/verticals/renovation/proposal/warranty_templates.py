"""Warranty language templates."""


class WarrantyTemplates:
    def render(self, months: int) -> str:
        if months <= 0:
            raise ValueError("warranty duration must be positive")
        return (
            f"Contractor warrants workmanship for {months} months after substantial completion. "
            "Manufacturer warranties for materials remain subject to their published terms."
        )
