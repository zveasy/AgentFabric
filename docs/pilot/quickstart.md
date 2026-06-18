# AgentFabric Pilot Quickstart

This pilot pack runs AgentFabric locally with a demo tenant, signed reference agents, governance approval, durable events, and a safe audit bundle.

## Run the demo

```bash
python scripts/run_demo_pilot.py
```

The command bootstraps `demo-tenant`, installs signed reference packages, starts a governed document review workflow, pauses for approval, resumes, records a decision, and writes `examples/demo_pilot_audit_bundle.json`.

## What to inspect

- Reference agents: `docs/pilot/reference_agents.md`
- Demo workflow definitions: `examples/workflows/`
- Marketplace fixtures: `examples/marketplace/seed_packages.json`
- Audit bundle behavior: `docs/pilot/audit_bundle.md`

The demo never persists raw sensitive values. Inputs use VEIL references such as `veil-ref-document`.
