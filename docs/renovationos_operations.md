# RenovationOS Operations Foundation

Generation R2 extends RenovationOS Foundation from preconstruction estimates and proposals into deterministic job execution records and change-order management.

## Architecture

R2 adds three packages:

- `agentfabric/verticals/renovation/jobs/`: accepted-proposal conversion, phases, status, and replay.
- `agentfabric/verticals/renovation/documentation/`: daily logs, field notes, photo metadata, issues, and daily summaries.
- `agentfabric/verticals/renovation/change_orders/`: scope deltas, rate-based pricing, approval history, documents, replay, and export.

All operations use the existing `RenovationFoundationService`, tenant context, JSON persistence interfaces, and hash-chained event store.

## Proposal-to-Job Flow

A job can only be created from a persisted proposal when the request records:

- `accepted: true`
- an explicit acceptance date
- an acceptance reference

The proposal timeline becomes an ordered set of job phases. The first phase is active and subsequent phases are pending. Job updates validate status and phase identifiers.

## Job Documentation

Daily logs contain a business date, summary, weather, crew hours, completed work, next steps, and references to photo and issue records.

Field notes contain a business date, author, source, note, and optional photo references.

Photo records accept metadata only:

- file name
- VEIL or storage reference
- SHA-256 digest
- caption
- capture date
- phase ID

Binary image content is rejected. Issue records track title, description, severity, status, date, and phase.

Daily summaries combine logs, notes, photos, and issues for a supplied date and produce a deterministic summary hash.

## Change Orders

Change orders may originate from:

- `customer_request`
- `field_note`
- `scope_change`

Field-note references must exist on the same tenant and job. Change-order lines reuse the original estimate's material rates, labor rate, labor assumptions, contingency percentage, and tax percentage. The standard change-order template is versioned as `change_order_standard` version `1.0.0`.

Statuses are `draft`, `sent`, `approved`, `rejected`, and `cancelled`. New records may be draft or sent. Only sent records can be approved or rejected. Decisions require an explicit business date and produce immutable approval history entries.

JSON and canonical text exports include deterministic hashes, template identifiers, costs, schedule changes, status, and approval history.

## Project History

`GET /renovation/jobs/{job_id}` includes the job plus:

- originating proposal and estimate
- daily logs
- field notes
- photo metadata
- issues
- change orders
- approval history
- change-order exports
- tenant-filtered event evidence
- deterministic history hash

This history is suitable for customer communication, warranty review, and dispute evidence.

## APIs

| Method | Path | Scope |
| --- | --- | --- |
| POST | `/renovation/jobs` | `renovation.jobs.write` |
| GET | `/renovation/jobs/{job_id}` | `renovation.jobs.read` |
| POST | `/renovation/jobs/{job_id}/daily-log` | `renovation.documentation.write` |
| POST | `/renovation/jobs/{job_id}/field-note` | `renovation.documentation.write` |
| POST | `/renovation/change-orders` | `renovation.change_orders.write` |
| GET | `/renovation/change-orders/{change_order_id}` | `renovation.change_orders.read` |
| POST | `/renovation/change-orders/{change_order_id}/approve` | `renovation.change_orders.approve` |
| POST | `/renovation/change-orders/{change_order_id}/reject` | `renovation.change_orders.approve` |
| POST | `/renovation/change-orders/{change_order_id}/export` | `renovation.change_orders.write` |

Read scopes are also available for documentation and change orders:

- `renovation.documentation.read`
- `renovation.change_orders.read`

## Example Job Request

```json
{
  "proposal_id": "proposal-...",
  "accepted": true,
  "accepted_date": "2026-07-01",
  "acceptance_reference": "signed-proposal-001"
}
```

## Example Change Order

```json
{
  "job_id": "job-...",
  "source_type": "customer_request",
  "source_reference": "customer-request-flooring",
  "title": "Premium flooring upgrade",
  "description": "Upgrade 50 square feet to premium flooring.",
  "lines": [
    {
      "description": "Premium flooring upgrade",
      "category": "flooring",
      "quantity": 50,
      "unit": "sqft"
    }
  ],
  "schedule_delta_days": 1,
  "status": "sent"
}
```

## Events and Audit

R2 emits durable tenant-scoped events for job creation/update, daily logs, field notes, photo metadata, issues, change-order creation, approval, rejection, and export.

Audit bundles include all R2 artifacts, template IDs, deterministic hashes, daily summaries, approval history, and export evidence without photo binary data.

## Marketplace

The package is now **RenovationOS Operations Foundation**, version `2.0.0`, with estimate, proposal, job documentation, change-order management, and project-history capabilities.
