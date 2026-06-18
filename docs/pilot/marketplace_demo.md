# Marketplace Demo

Pilot seed package examples live in `examples/marketplace/seed_packages.json`.

The demo bootstrap also generates deterministic signed package fixtures for all reference agents using local development keys. Production marketplace installs still require trusted publishers, valid signatures, entitlements, tenant context, RBAC, and quota checks.

Use:

```bash
python scripts/bootstrap_demo_tenant.py
```

The output includes installed reference packages and signature metadata.
