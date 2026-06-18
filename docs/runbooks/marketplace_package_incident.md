# Marketplace Package Incident Runbook

1. Identify package id, version, publisher, installs, and entitlements.
2. Revoke or block the affected package version.
3. Stop runtime jobs for the package.
4. Notify impacted tenant admins.
5. Preserve scan results, signature evidence, and event timeline.

Rollback to a revoked/vulnerable version requires explicit admin override and incident approval.
