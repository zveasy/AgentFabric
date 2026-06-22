# Architecture

The repository separates immutable domain models, service orchestration, FastAPI routes, event declarations, RBAC scopes, audit hooks, and metrics hooks.

Sensitive values are represented by VEIL references and are never persisted directly.
