# RenovationOS Buildout

Generation 18 materializes the first three RenovationOS repositories under `platforms/renovation_os/repositories/`.

## reno_estimator

Models project intake, room scope, materials, labor assumptions, estimate line items, estimate results, margin scenarios, and risk adjustments.

## change_order_agent

Models change orders, scope/cost/schedule deltas, approval status, customer approval, contractor acknowledgement, and audit records. It declares `reno_estimator` as a dependency.

## contractor_command_center

Models contractor profiles, crews, job tasks, attendance, quality issues, licenses, insurance, and payment milestones. It declares the RenovationOS command-center dependencies.

## Generated repository contract

Each repository contains:

- Domain models and a service boundary.
- FastAPI application and OpenAPI stub.
- Event, RBAC, audit, and metrics declarations.
- Unit test scaffolding.
- README, architecture, API, and deployment documentation.
- `pyproject.toml`, Docker, Compose, CI, example config, package metadata, and repository manifest.

Regenerate the checked-in references with:

```bash
python scripts/materialize_renovation_os.py
```

The script uses the same plan, dry-run, approval, and execution engine as the API and verifies the event chain before exiting.
