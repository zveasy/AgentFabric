from .base_agent import SoftwareStageAgent


class ReleaseAgent(SoftwareStageAgent):
    stage = "release_validation"
