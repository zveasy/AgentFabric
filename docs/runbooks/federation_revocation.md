# Federation Revocation Runbook

1. Revoke the trust agreement through `/federation/agreements/{id}/revoke`.
2. Confirm `federation.agreement.revoked` and `federation.remote_org.blocked` events.
3. Stop pending remote delegation jobs.
4. Block marketplace installs from the revoked source.
5. Export audit evidence for the tenant.

Revocation must block discovery, messages, delegation, and remote execution immediately.
