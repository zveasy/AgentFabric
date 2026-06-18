# Deployment Runbook

1. Run `python scripts/release_validate.py`.
2. Build the image and scan it.
3. Configure production env: non-default JWT secret, durable DB, queue backend, VEIL API URL, strict signing.
4. Apply migrations before shifting traffic.
5. Deploy API and worker separately.
6. Verify `/ready`, `/health/runtime`, `/health/queues`, and `/metrics`.
7. Issue bootstrap/admin credentials through the approved secret path.

Rollback: restore the previous image, stop workers, verify event integrity, and resume workers only after queue health is green.
