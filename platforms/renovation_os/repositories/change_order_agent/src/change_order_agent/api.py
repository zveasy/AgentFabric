"""FastAPI route stubs."""

from fastapi import APIRouter, FastAPI

router = APIRouter(tags=["renovation-os"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "repository": "change_order_agent"}


app = FastAPI(title="change_order_agent", version="0.1.0")
app.include_router(router)
