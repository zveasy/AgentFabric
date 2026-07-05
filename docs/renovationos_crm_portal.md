# RenovationOS CRM and Customer Portal

Generation R5 extends RenovationOS Operations Foundation into customer acquisition and customer experience. Lead, opportunity, follow-up, appointment, communication, and portal outputs remain deterministic, tenant scoped, replayable, and independent of external AI providers.

## Architecture

- `agentfabric/verticals/renovation/leads/` owns intake sources and lead lifecycle transitions.
- `agentfabric/verticals/renovation/crm/` owns opportunities, follow-ups, appointment requests, and site visits.
- `agentfabric/verticals/renovation/communications/` owns calls, email, text, note, and portal message history.
- `agentfabric/verticals/renovation/customer_portal/` owns allowlist-based customer projections and visibility validation.
- `RenovationFoundationService` enforces tenant and object ownership, persists replay inputs, and emits durable events.

## Lead Lifecycle

Lead sources support manual entry, website forms, referrals, and phone notes.

The supported status sequence is:

```text
new
  -> contacted
  -> appointment_requested
  -> estimate_scheduled
  -> proposal_sent
  -> won | lost
```

Some adjacent transitions are optional, such as moving directly from contacted to estimate scheduled. Terminal won and lost leads cannot be reopened. Lost leads require a reason. Only won leads can be converted to customers.

## Opportunities and Follow-Ups

Opportunities track project type, expected value, probability, stage, expected close date, and weighted value.

Follow-up tasks produce deterministic due dates and reminder dates. Appointment requests can target leads or customers. Site visits must reference a tenant-owned appointment.

## Communications

Communication channels are:

- call;
- email;
- text;
- note;
- portal.

Messages record direction and visibility. Customer-visible messages can appear in portal history. Internal messages remain in audit and operational history but are excluded from customer projections.

## Customer Visibility Policy

The default policy ID is `renovation-customer-visibility-v1`.

Portal views are built from an explicit allowlist. They can include:

- project title and status;
- scope summary;
- approved timeline and current phase;
- recent non-internal progress logs;
- explicitly approved photos;
- approved change orders;
- customer invoice and payment status;
- customer-visible communications.

They exclude:

- internal margin and profitability data;
- vendor costs and payables;
- internal notes and messages;
- unapproved photos;
- schedule conflicts and internal risk alerts;
- audit and artifact hashes;
- RBAC and ownership metadata.

The portal service validates projections and fails closed if forbidden internal fields appear.

## APIs

| Method | Path | Required scope |
| --- | --- | --- |
| POST | `/renovation/leads` | `renovation.leads.write` |
| GET | `/renovation/leads/{lead_id}` | `renovation.leads.read` |
| POST | `/renovation/leads/{lead_id}/status` | `renovation.leads.write` |
| POST | `/renovation/leads/{lead_id}/convert` | `renovation.leads.write` |
| POST | `/renovation/opportunities` | `renovation.crm.write` |
| GET | `/renovation/opportunities/{opportunity_id}` | `renovation.crm.read` |
| POST | `/renovation/opportunities/{opportunity_id}/stage` | `renovation.crm.write` |
| POST | `/renovation/follow-ups` | `renovation.crm.write` |
| POST | `/renovation/appointments` | `renovation.crm.write` |
| POST | `/renovation/site-visits` | `renovation.crm.write` |
| POST | `/renovation/customer-messages` | `renovation.communications.write` |
| GET | `/renovation/customers/{customer_id}/portal-view` | `renovation.portal.read` |
| GET | `/renovation/jobs/{job_id}/customer-status` | `renovation.portal.read` |

Portal and customer-status reads require a deterministic `generated_date` query parameter.

## Replay and Audit

Lead creation inputs and ordered status updates are retained. Opportunity stage changes are replayed in order. Portal generation stores its policy, project projection inputs, communication inputs, and final artifact.

Audit bundles include leads, converted customers, opportunities, follow-ups, appointments, site visits, messages, communication records, portal generation inputs, policy identifiers, deterministic hashes, and replay evidence.

## Marketplace

RenovationOS Operations Foundation version `5.0.0` adds lead intake, CRM, follow-up workflows, appointments, customer communication history, and customer-safe portal views.
