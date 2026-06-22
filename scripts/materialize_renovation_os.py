"""Materialize the Generation 18 RenovationOS reference repositories."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentfabric.enterprise import TenantContext  # noqa: E402
from agentfabric.events import EventStore  # noqa: E402
from agentfabric.persistence import MemoryPersistenceStore  # noqa: E402
from agentfabric.repository_execution import RepositoryExecutionEngine  # noqa: E402


REPOSITORIES = ("reno_estimator", "change_order_agent", "contractor_command_center")


def main() -> int:
    persistence = MemoryPersistenceStore()
    event_store = EventStore(persistence=persistence)
    engine = RepositoryExecutionEngine(
        persistence=persistence,
        event_store=event_store,
        output_root=ROOT / "platforms" / "renovation_os" / "repositories",
        platform_root=ROOT / "platforms" / "renovation_os",
        tenant_subdirectories=False,
    )
    context = TenantContext(
        tenant_id="agentfabric-reference",
        organization_id="agentfabric",
        principal_id="generation-18-release",
        roles=("factory:admin", "factory:execute"),
    )
    for repository_name in REPOSITORIES:
        plan = engine.plan(context, repository_name)
        engine.dry_run(context, plan.execution_id)
        engine.approve(context, plan.execution_id)
        engine.execute(context, plan.execution_id)
    if not event_store.validate_integrity():
        raise RuntimeError("reference repository event chain failed validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
