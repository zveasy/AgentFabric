"""Payment schedule generation."""

from agentfabric.verticals.renovation.models import PaymentSchedule


class PaymentTerms:
    def build(
        self,
        total: float,
        terms: list[dict[str, object]],
    ) -> tuple[PaymentSchedule, ...]:
        schedules = []
        allocated = 0.0
        for index, term in enumerate(terms):
            percentage = float(term["percentage"])
            amount = round(total * percentage / 100, 2)
            if index == len(terms) - 1:
                amount = round(total - allocated, 2)
            allocated = round(allocated + amount, 2)
            schedules.append(PaymentSchedule(str(term["label"]), percentage, amount))
        return tuple(schedules)
