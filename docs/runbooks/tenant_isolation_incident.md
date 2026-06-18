# Tenant Isolation Incident Runbook

1. Disable affected principal tokens.
2. Export tenant-scoped events and memory operation metadata.
3. Verify no cross-tenant durable records were created.
4. Rotate impacted credentials.
5. Run tenant isolation tests before restoring access.

Do not disclose raw sensitive values outside VEIL/Aegis-controlled channels.
