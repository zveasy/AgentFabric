# VEIL Connectivity Failure Runbook

1. Confirm VEIL endpoint and credentials.
2. Check policy latency and failures in metrics.
3. Pause risky runtime, federation, marketplace, and governance actions.
4. Retry only idempotent operations after VEIL recovers.
5. Preserve audit events and notify security owner.

AgentFabric must not substitute local trust decisions for VEIL decisions.
