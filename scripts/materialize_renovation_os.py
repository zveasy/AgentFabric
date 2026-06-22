"""Materialize the Generation 18 RenovationOS reference repositories."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentfabric.enterprise import TenantContext  # noqa: E402
from agentfabric.build_workers import BuildWorkerService  # noqa: E402
from agentfabric.events import EventStore  # noqa: E402
from agentfabric.persistence import MemoryPersistenceStore  # noqa: E402
from agentfabric.repository_execution import RepositoryExecutionEngine  # noqa: E402


REPOSITORIES = ("reno_estimator", "change_order_agent", "contractor_command_center")


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary)
        persistence = MemoryPersistenceStore()
        event_store = EventStore(persistence=persistence)
        engine = RepositoryExecutionEngine(
            persistence=persistence,
            event_store=event_store,
            output_root=staging,
            platform_root=ROOT / "platforms" / "renovation_os",
            tenant_subdirectories=False,
        )
        builds = BuildWorkerService(
            persistence=persistence,
            event_store=event_store,
            execution_engine=engine,
            output_root=staging,
            tenant_subdirectories=False,
        )
        context = TenantContext(
            tenant_id="agentfabric-reference",
            organization_id="agentfabric",
            principal_id="generation-19-release",
            roles=("factory:admin", "factory:execute"),
        )
        for repository_name in REPOSITORIES:
            plan = engine.plan(context, repository_name)
            engine.dry_run(context, plan.execution_id)
            engine.approve(context, plan.execution_id)
            engine.execute(context, plan.execution_id)
            build = builds.plan(context, plan.execution_id)
            builds.dry_run(context, str(build["build_id"]))
            builds.approve(context, str(build["build_id"]))
            builds.execute(context, str(build["build_id"]))
            builds.review(context, str(build["build_id"]))
        if not event_store.validate_integrity():
            raise RuntimeError("reference repository event chain failed validation")
        destination = ROOT / "platforms" / "renovation_os" / "repositories"
        for repository_name in REPOSITORIES:
            source = staging / repository_name
            target = destination / repository_name
            target.mkdir(parents=True, exist_ok=True)
            for source_file in source.rglob("*"):
                if source_file.is_file():
                    relative = source_file.relative_to(source)
                    target_file = target / relative
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source_file, target_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
