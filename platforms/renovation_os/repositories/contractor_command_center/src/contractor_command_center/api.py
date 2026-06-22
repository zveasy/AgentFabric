"""FastAPI route stubs."""

from fastapi import APIRouter, FastAPI

router = APIRouter(tags=["renovation-os"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "repository": "contractor_command_center"}


app = FastAPI(title="contractor_command_center", version="0.1.0")
app.include_router(router)
