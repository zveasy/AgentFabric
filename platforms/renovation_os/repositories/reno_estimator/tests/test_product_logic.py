from reno_estimator.models import LaborAssumption, ProjectIntake, RoomScope
from reno_estimator.service import EstimatorService


def test_estimate_scenarios_are_deterministic() -> None:
    intake = ProjectIntake("p1", "local", (RoomScope("Kitchen", 100, "standard", 10),))
    result = EstimatorService().estimate(
        intake,
        LaborAssumption(50),
        risk_buffer_percentage=10,
        profit_margin_target=20,
    )
    assert result.scenarios == {"low": 2103.75, "base": 2337.5, "high": 2688.12}
    assert result.confidence_score == 0.867


def test_invalid_intake_fails_closed() -> None:
    intake = ProjectIntake("", "", ())
    try:
        EstimatorService().estimate(intake, LaborAssumption(50))
    except ValueError:
        return
    raise AssertionError("invalid intake was accepted")
