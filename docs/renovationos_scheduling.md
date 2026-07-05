# RenovationOS Scheduling and Crew Coordination

Generation R3 extends RenovationOS Operations Foundation from active job documentation into deterministic execution planning. Schedules are derived from accepted jobs and persisted inputs. No external planning or AI provider is required.

## Architecture

- `agentfabric/verticals/renovation/scheduling/` owns phase dependencies, date calculation, conflict detection, delay impacts, customer summaries, and schedule hashes.
- `agentfabric/verticals/renovation/crews/` owns crews, members, availability windows, and assignments.
- `agentfabric/verticals/renovation/deliveries/` owns material delivery dates and status.
- `RenovationFoundationService` enforces tenant ownership, persists inputs and artifacts, emits events, and records replay evidence.

All dates use ISO `YYYY-MM-DD` values. Durations and dependency lags use calendar days.

## Scheduling Flow

1. Create an accepted RenovationOS job.
2. Create a schedule with a start date.
3. Define optional phase-duration overrides or explicit dependencies.
4. Create crews and availability windows.
5. Assign crews to schedule phases.
6. Record material deliveries.
7. Recalculate the schedule.
8. Retrieve the customer-facing summary.

When dependencies are omitted, phases use the job sequence and finish-to-start dependencies. Cycles, unknown phases, negative lags, and non-positive durations fail closed.

## Delay Analysis

Recalculation evaluates:

- overlapping crew assignments;
- unavailable or limited crew windows;
- delayed or cancelled material deliveries;
- material arrival after its required date;
- downstream dependency impact.

Late deliveries shift the affected phase to the effective delivery date. Crew conflicts add deterministic blocked-day adjustments. Downstream phases are recalculated in topological order.

Each result includes original and projected completion dates, blocked phase reasons, normalized conflicts, delay summaries, a revision number, and a deterministic schedule hash.

## Replay

Schedule creation inputs are persisted with the original artifact. Every recalculation stores the exact assignment, availability, delivery, and request snapshots used for that revision.

Replay recreates the base schedule and applies each stored recalculation in revision order. A mismatch with the persisted schedule fails closed.

## APIs

| Method | Path | Required scope |
| --- | --- | --- |
| POST | `/renovation/schedules` | `renovation.scheduling.write` |
| GET | `/renovation/schedules/{schedule_id}` | `renovation.scheduling.read` |
| POST | `/renovation/schedules/{schedule_id}/recalculate` | `renovation.scheduling.write` |
| POST | `/renovation/crews` | `renovation.crews.write` |
| GET | `/renovation/crews/{crew_id}` | `renovation.crews.read` |
| POST | `/renovation/crews/{crew_id}/availability` | `renovation.crews.write` |
| POST | `/renovation/crew-assignments` | `renovation.crews.write` |
| POST | `/renovation/material-deliveries` | `renovation.deliveries.write` |
| GET | `/renovation/jobs/{job_id}/schedule-summary` | `renovation.scheduling.read` |

All routes require existing AgentFabric authentication and tenant context.

## Example

```json
{
  "job_id": "job-example",
  "start_date": "2026-07-06",
  "phase_durations": {
    "phase-01": 3
  }
}
```

```json
{
  "schedule_id": "schedule-example",
  "phase_id": "phase-01",
  "material": "Kitchen cabinets",
  "quantity": 1,
  "unit": "lot",
  "required_date": "2026-07-06",
  "expected_date": "2026-07-09",
  "status": "delayed"
}
```

## Events and Audit

R3 emits durable events for schedule creation and recalculation, crew creation and assignment, availability changes, delivery changes, and detected delays.

Audit bundles include schedules, phases, dependencies, schedule hashes, crew records, assignments, availability, deliveries, delay impacts, summaries, and recalculation evidence. Every collection is tenant filtered.

## Marketplace

RenovationOS Operations Foundation version `3.0.0` added project scheduling, crew coordination, material delivery tracking, conflict detection, blocked-phase detection, and delay impact analysis. Later versions add financial intelligence, CRM, and customer portal views.
