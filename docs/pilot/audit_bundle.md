# Audit Bundle

Generation 11 adds `agentfabric/audit_bundle/` for customer-safe pilot exports.

The exporter includes:

- tenant summary
- workflow timeline
- proposal and decision records
- package install records
- event hash-chain summary
- VEIL audit references
- reputation summary
- runtime job summary

The bundle redactor blocks raw sensitive values and keeps sensitive material represented as VEIL references.
