# Migration Runbook

1. Take a DB backup.
2. Run migration dry-run validation through `MigrationRunner(...).apply(dry_run=True)`.
3. Apply migrations in a maintenance window for production.
4. Verify schema version and `/health/persistence`.
5. Run event integrity validation.

Abort on any migration error. Do not start workflow recovery until integrity checks pass.
