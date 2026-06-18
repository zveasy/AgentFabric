# Security Hardening Checklist

## Required For Production

- Auth/JWT validation: non-default JWT secret, expiry, token persistence, revocation.
- RBAC enforcement: role scopes assigned intentionally; service accounts cannot escalate roles.
- Tenant context enforcement: protected APIs require authenticated tenant context.
- Secret management: secrets supplied through deployment secret stores, never committed.
- Package signatures: strict signing enabled; unsigned marketplace installs rejected in production.
- Dependency scanning: package dependency graph and permission scanner run before install.
- Payload size and content limits: reject raw sensitive keys such as `secret`, `raw`, `password`, and `token_value`; enforce gateway body limits at ingress.
- Raw sensitive data: persist VEIL references, not raw restored values.
- Audit logging: durable event ledger and tenant audit exports enabled.
- Event integrity: run hash-chain validation before recovery and during release validation.
- Replay protection: federation messages require nonce uniqueness and TTL.
- Federation revocation: revoked or expired agreements block discovery, messages, and delegation.
- Worker isolation: non-root containers, resource limits, queue scopes, worker heartbeat monitoring.
- Local/dev restrictions: local unsigned packages and mock dependencies only outside production.

## Release Gate

Run:

```bash
python scripts/release_validate.py
```

Production deployment should not proceed unless every check passes and current VEIL/Aegis external dependencies are reachable under the deployment's operating model.
