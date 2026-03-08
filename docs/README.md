# AgentFabric documentation

- [Agent Protocol Layer](agent-protocol-layer.md) — Interoperability standard (TCP/IP of AI agents)
- [Architecture](architecture.md) — Runtime components and data flow
- [Manifest Reference](manifest-reference.md) — Agent manifest schema and fields
- [SDK Guide](sdk-guide.md) — Building agents with the Python SDK
- [CLI Reference](cli-reference.md) — `agentfabric` commands and config
- [Security Model](security-model.md) — Permissions, sandbox, audit, versioning

## Implemented API (production server)

The FastAPI server (`agentfabric.server`) provides:

- **System:** `GET /health`, `GET /ready` (DB + Redis readiness)
- **Auth:** `POST /auth/principals/register` (with `role`), `POST /auth/token/issue`, `POST /auth/token/rotate`
- **Registry:** `POST /registry/publish`, `GET /registry/list` (query, category, permission, `private_only`), `POST /registry/install`, `GET/POST /registry/packages/{fqid}/reviews`, `GET /registry/packages/{fqid}/reviews/summary`
- **Billing:** `POST /billing/events` (idempotent), `GET /billing/invoice`, `POST /billing/settle`
- **Queue:** `POST /queue/enqueue`, `POST /queue/dequeue`
- **Audit:** `POST /audit/append`, `GET /audit/export` (SIEM-style; requires `audit.export`)
- **Workflows (Phase 3):** `POST /workflows/run` (DAG with idempotency)
- **Admin (Phase 4):** `POST /admin/principals/{id}/role` (RBAC; requires `rbac.assign_role`)
- **Agent Projects (AgentForge):**
  - `POST /projects`, `GET /projects`, `GET /projects/{namespace}/{project_id}`
  - `POST /projects/{namespace}/{project_id}/maintainers`, `POST /projects/{namespace}/{project_id}/branches`
  - `POST /projects/{namespace}/{project_id}/contributions`
  - `POST /projects/{namespace}/{project_id}/contributions/{id}/evaluate`
  - `POST /projects/{namespace}/{project_id}/contributions/{id}/review`
  - `GET /projects/{namespace}/{project_id}/releases`
