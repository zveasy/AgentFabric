# RenovationOS Product Logic

Generation 19 advances the first RenovationOS repositories from scaffolds to working alpha implementations.

## reno_estimator

The estimator validates project intake, normalizes room names, applies deterministic material-category multipliers, calculates labor with a location-adjustment placeholder, adds a risk buffer, applies a target margin, and exports low/base/high scenarios with a confidence score.

Pricing uses local tables only. No external pricing API is called.

## change_order_agent

The change-order service creates scope, cost, and schedule deltas and records customer approval, contractor acknowledgement, and audit history.

Allowed transitions are:

```text
draft -> sent
sent -> approved | rejected
approved -> acknowledged
acknowledged -> closed
```

All other transitions fail closed.

## contractor_command_center

The contractor service validates profiles and tracks licenses, insurance, crews, tasks, attendance, quality issues, and payment milestones. Reliability scoring combines on-time attendance, task completion, quality issues, document completeness, and milestone status using fixed weights.

## Reference builds

The checked-in repositories under `platforms/renovation_os/repositories/` contain product logic, route tests, service tests, build evidence, security evidence, and private marketplace maturity metadata.

Regenerate them with:

```bash
python scripts/materialize_renovation_os.py
```

The script performs scaffold execution, build planning, dry-run, approval, execution, review, and event-chain validation in an isolated staging directory before synchronizing output.
