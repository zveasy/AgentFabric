"""Connector runtime and action permissions."""

from __future__ import annotations


CONNECTOR_SCOPES = {
    "connectors:read",
    "connectors:write",
    "connectors:execute",
    "connectors:admin",
    "credentials:read",
    "credentials:write",
    "credentials:rotate",
}

ACTION_PERMISSIONS = {
    "gmail.read",
    "gmail.send",
    "calendar.read",
    "calendar.write",
    "github.read",
    "github.write",
    "jira.read",
    "jira.write",
    "slack.read",
    "slack.write",
    "servicenow.read",
    "servicenow.write",
    "s3.read",
    "s3.write",
    "custom_http.execute",
    "teams.read",
    "teams.write",
    "salesforce.read",
    "salesforce.write",
    "sharepoint.read",
    "sharepoint.write",
}

PREFIXES = {
    "google_calendar": "calendar",
}


def permission_for(connector_type: str, action: str) -> str:
    prefix = PREFIXES.get(connector_type, connector_type)
    normalized = action.lower()
    if connector_type == "custom_http":
        permission = "custom_http.execute"
    elif normalized in {"send", "write", "create", "update", "delete"}:
        permission = f"{prefix}.{'send' if connector_type == 'gmail' and normalized == 'send' else 'write'}"
    else:
        permission = f"{prefix}.read"
    if permission not in ACTION_PERMISSIONS:
        raise ValueError(f"unsupported connector action permission: {permission}")
    return permission


def require_permissions(granted: set[str], required: set[str]) -> None:
    if not required.issubset(granted):
        missing = ", ".join(sorted(required - granted))
        raise PermissionError(f"missing connector permissions: {missing}")
