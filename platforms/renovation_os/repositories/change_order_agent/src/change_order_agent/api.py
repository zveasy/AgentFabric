"""Change-order API."""

from fastapi import APIRouter, FastAPI

from .service import ChangeOrderService

router = APIRouter(tags=["change-orders"])
service = ChangeOrderService()


@router.post("/change-orders")
def create_change_order(payload: dict[str, object]) -> dict[str, object]:
    return service.create(
        str(payload["change_order_id"]),
        str(payload["description"]),
        float(payload["cost_delta"]),
        int(payload["schedule_days"]),
    ).export()


app = FastAPI(title="change_order_agent", version="0.2.0")
app.include_router(router)
