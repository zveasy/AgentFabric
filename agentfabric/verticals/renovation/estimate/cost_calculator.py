"""Deterministic estimate totals."""


class CostCalculator:
    def calculate(
        self,
        material_total: float,
        labor_total: float,
        contingency_percentage: float,
        tax_percentage: float,
    ) -> dict[str, float]:
        if not 0 <= contingency_percentage <= 100:
            raise ValueError("contingency percentage must be between 0 and 100")
        if not 0 <= tax_percentage <= 100:
            raise ValueError("tax percentage must be between 0 and 100")
        subtotal = round(material_total + labor_total, 2)
        contingency = round(subtotal * contingency_percentage / 100, 2)
        taxable_amount = round(material_total + contingency, 2)
        tax = round(taxable_amount * tax_percentage / 100, 2)
        return {
            "subtotal": subtotal,
            "contingency": contingency,
            "taxable_amount": taxable_amount,
            "tax": tax,
            "total": round(subtotal + contingency + tax, 2),
        }
