# Pilot FAQ

## Does the demo require Redis, Stripe, or external services?

No. The pilot scripts use local in-memory services and deterministic development signing keys.

## Does the demo bypass production safety gates?

No. It runs in local mode and preserves the same boundaries: tenant scope, governance records, signed package fixtures, durable events, and VEIL references.

## Where is the one-command demo?

Run `python scripts/run_demo_pilot.py`.

## Can customers inspect the audit evidence?

Yes. The demo writes `examples/demo_pilot_audit_bundle.json` and prints the same evidence to stdout.

## Are raw sensitive values exported?

No. The audit bundle redactor rejects raw sensitive fields and the demo uses VEIL references instead of raw values.
