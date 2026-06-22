"""Contractor command-center API."""

from fastapi import APIRouter, FastAPI

from .models import ContractorProfile
from .service import ContractorService

router = APIRouter(tags=["contractors"])
service = ContractorService()


@router.post("/contractors/reliability")
def reliability(payload: dict[str, object]) -> dict[str, float]:
    profile = ContractorProfile(str(payload["contractor_id"]), str(payload["name"]))
    return {"reliability_score": service.reliability_score(profile)}


app = FastAPI(title="contractor_command_center", version="0.2.0")
app.include_router(router)
