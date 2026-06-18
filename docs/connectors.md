# Enterprise Connector Runtime

Generation 17 adds a secure connector control plane in `agent_connectors/`. It complements the VEIL-mediated adapter framework in `agentfabric/connectors/`.

## Architecture

Agents never call enterprise systems directly. Calls flow through `ConnectorExecutionService`:

1. Require tenant context and an enabled connector.
2. Validate agent and connector action permissions.
3. Resolve a tenant-isolated credential reference through `CredentialVault`.
4. Evaluate connector, agent, action, credential, risk, and package trust policy.
5. Enforce rate, timeout, payload, response, domain, and HTTP method limits.
6. Ask VEIL to authorize and sanitize the request.
7. Invoke the connector adapter without exposing credential material to the agent.
8. Normalize the result and emit durable AgentFabric and VEIL audit events.

Production execution fails closed when required policy or VEIL services are unavailable.

## Connector Manifests

Manifests are immutable and versioned. They declare connector type, supported actions, required permissions, credential type, rate limits, risk level, tenant scope, network restrictions, and trust score.

Supported types include Gmail, Google Calendar, Slack, Teams, Jira, GitHub, Salesforce, ServiceNow, SharePoint, S3, and custom HTTP.

## Credential Model

`CredentialVault` returns only reference IDs such as `vault-ref:credential-id:v1`. Persisted records contain lifecycle metadata, never plaintext secrets. The local backend keeps development secrets in process memory. Production deployments supply a vault backend implementing the credential backend protocol.

Credentials are tenant isolated and support create, rotate, and revoke operations.

## Security Model

Execution policies can restrict:

* tenants
* agents
* connectors
* actions
* credential types
* maximum connector risk
* minimum marketplace package trust
* required VEIL checks

Sandbox rules enforce request and response size limits, timeouts, allowed and blocked domains, HTTP methods, credential exfiltration prevention, and tenant isolation.

## APIs

* `POST /connectors/register`
* `GET /connectors`
* `GET /connectors/{connector_id}`
* `POST /connectors/{connector_id}/enable`
* `POST /connectors/{connector_id}/disable`
* `POST /connectors/{connector_id}/execute`
* `POST /credentials`
* `POST /credentials/{credential_id}/rotate`
* `POST /credentials/{credential_id}/revoke`

## Events

The durable event ledger records connector registration, enablement, disablement, execution requests, allow and deny decisions, completion and failure, plus credential creation, rotation, and revocation.

## Marketplace Review

Marketplace packages must explicitly declare connector requirements and permissions. Publication fails when permissions are undeclared, exceed the required connector manifests, request an unreviewed high-risk connector, or depend on a connector below the configured trust threshold.

Audit bundles include manifests, tenant enablement, executions, denials, credential lifecycle references, policy decisions, and tenant isolation evidence.
