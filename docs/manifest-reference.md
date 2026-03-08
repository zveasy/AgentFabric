# Manifest Reference

Agent packages are described by a **manifest** (YAML or JSON). The runtime validates it against the [manifest schema](../agents/manifest_schema/manifest.v1.schema.json) at load and install.

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique agent id (snake_case, pattern `^[a-z][a-z0-9_]*$`). |
| `version` | string | Semantic version (e.g. `1.0`, `2.1.0-beta`). |
| `description` | string | Human-readable description. |

## Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `manifest_version` | string | Schema version; use `"1"` for v1. |
| `permissions` | array of string | Permission scopes the agent may use. Deny by default. |
| `tools` | array of string | Tool names the agent may invoke. Must be allowed by permissions. |
| `inputs` | array of string | Declared input names (semantic). |
| `outputs` | array of string | Declared output names (semantic). |
| `entrypoint` | string | Entrypoint for execution (e.g. `agent:run` or `main:run`). |
| `category` | string | Marketplace category (e.g. Finance, DevOps). |
| `author` | string | Author or organization. |
| `license` | string | SPDX or custom license name. |

## Example

```yaml
name: financial_analysis_agent
version: 1.0
description: Performs financial modeling and forecasting

permissions:
  - read_market_data
  - write_reports

inputs:
  - financial_data

outputs:
  - forecast
  - risk_assessment

tools:
  - pandas
  - numpy
  - market_api

entrypoint: agent:run
category: Finance
```

## Validation

- The runtime loads the manifest at **install** and **load**. Invalid manifests (missing required fields, invalid patterns) cause load/install to fail.
- Tool calls are checked against `tools`; the runtime returns `permission_denied` if the tool is not listed.

## Schema

Machine-readable schema: [agents/manifest_schema/manifest.v1.schema.json](../agents/manifest_schema/manifest.v1.schema.json).
