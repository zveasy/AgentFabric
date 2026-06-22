"""Audit hook that stores references, never raw sensitive values."""

def audit_record(action: str, veil_reference: str) -> dict[str, str]:
    if not veil_reference.startswith("veil:"):
        raise ValueError("VEIL reference required")
    return {"action": action, "veil_reference": veil_reference}
