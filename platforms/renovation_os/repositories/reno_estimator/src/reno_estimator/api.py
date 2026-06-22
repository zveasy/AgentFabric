"""Estimator API."""

from fastapi import APIRouter, FastAPI

from .models import LaborAssumption, ProjectIntake, RoomScope
from .service import EstimatorService

router = APIRouter(tags=["estimates"])
service = EstimatorService()


@router.post("/estimates")
def create_estimate(payload: dict[str, object]) -> dict[str, object]:
    rooms = tuple(RoomScope(**item) for item in payload["rooms"])
    intake = ProjectIntake(str(payload["project_id"]), str(payload["location"]), rooms)
    labor = LaborAssumption(**payload["labor"])
    return service.estimate(intake, labor).export()


app = FastAPI(title="reno_estimator", version="0.2.0")
app.include_router(router)
