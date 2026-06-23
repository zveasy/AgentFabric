# RenovationOS Foundation

RenovationOS Foundation is AgentFabric's first deterministic vertical package. It produces renovation estimates and customer proposals entirely offline from persisted inputs, fixed rate tables, and versioned templates.

## Architecture

The package is located at `agentfabric/verticals/renovation/`:

- `models/`: serializable customer, project, room, scope, estimate, payment, timeline, and proposal models.
- `estimate/`: scope parsing, material and labor estimation, cost calculation, and estimate construction.
- `proposal/`: scope formatting, payment schedules, timelines, warranties, rendering, and proposal construction.
- `templates/`: versioned JSON proposal and remodel templates.
- `events/`: durable event declarations.
- `api/`: endpoint and scope contracts.

`RenovationFoundationService` owns tenant filtering, persistence, event emission, replay verification, proposal export, and foundation marketplace metadata.

## Estimate Flow

1. Normalize the scope description into ordered scope items.
2. Apply explicit quantities or room-area defaults.
3. Apply local material rates and labor productivity assumptions.
4. Calculate material and labor totals.
5. Apply contingency.
6. Apply tax to material and contingency costs.
7. Generate a content-derived estimate ID and persist the input and artifact.

Default rate tables are versioned as `renovation-rates-v1`. Callers can override rates and labor assumptions in the request.

## Proposal Flow

1. Load a tenant-owned persisted estimate.
2. Load a versioned proposal template.
3. Format scope, payment schedule, timeline, warranty, and clauses.
4. Render canonical proposal text.
5. Generate a content-derived proposal ID and persist the input and artifact.

Timeline output uses ordered phase durations rather than current dates. Identical inputs and template versions therefore produce identical proposals.

## Models

Primary models are `Customer`, `Project`, `Room`, `ScopeItem`, `MaterialLine`, `LaborLine`, `Estimate`, `PaymentSchedule`, `Timeline`, and `Proposal`. Each supports `as_dict()` and canonical `export_json()`.

## APIs

All routes require JWT authentication and tenant context.

| Method | Path | Scope |
| --- | --- | --- |
| POST | `/renovation/estimate` | `renovation.estimate.write` |
| GET | `/renovation/estimate/{estimate_id}` | `renovation.estimate.read` |
| POST | `/renovation/proposal` | `renovation.proposal.write` |
| GET | `/renovation/proposal/{proposal_id}` | `renovation.proposal.read` |
| POST | `/renovation/proposal/export` | `renovation.proposal.write` |

## Example Estimate

```json
{
  "project_id": "project-kitchen-1",
  "scope_description": "Cabinet replacement\nFlooring replacement",
  "rooms": [
    {
      "name": "Kitchen",
      "length_ft": 20,
      "width_ft": 15,
      "quantity": 1,
      "notes": "Main floor"
    }
  ],
  "quantities": {
    "cabinetry": 10,
    "flooring": 300
  },
  "labor_rate": 65,
  "contingency_percentage": 10,
  "tax_percentage": 6
}
```

The response includes material lines, labor lines, subtotal, contingency, taxable amount, tax, and grand total.

## Example Proposal

```json
{
  "estimate_id": "estimate-...",
  "customer": {
    "customer_id": "customer-1",
    "name": "Jordan Customer",
    "email": "jordan@example.com",
    "phone": "555-0100",
    "address": "100 Main Street"
  },
  "project": {
    "project_id": "project-kitchen-1",
    "title": "Kitchen Remodel",
    "property_address": "100 Main Street",
    "notes": "Occupied residence"
  },
  "template_id": "standard_proposal"
}
```

Export request:

```json
{
  "proposal_id": "proposal-...",
  "format": "text"
}
```

## Templates

- `standard_proposal`
- `premium_proposal`
- `light_remodel_template`
- `full_remodel_template`

Templates define payment percentages, warranty duration, project phases, style, version, and standard clauses. Payment percentages must total 100.

## Replay and Audit

Estimate and proposal records persist both original input and generated artifact. Replay reconstructs the artifact and fails if canonical output diverges. Events are tenant-scoped and hash-chain compatible:

- `renovation.estimate_created`
- `renovation.estimate_updated`
- `renovation.proposal_generated`
- `renovation.proposal_exported`

Audit bundles include estimate artifacts, proposal artifacts, template identifiers, cost breakdowns, timelines, and exports.

## Marketplace

The internal package catalog registers **RenovationOS Foundation** in the Construction and Operations categories. Metadata declares offline deterministic execution, estimate and proposal capabilities, tenant isolation, and replay support.
