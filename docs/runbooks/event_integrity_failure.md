# Event Integrity Failure Runbook

1. Stop workflow recovery and federation/runtime replay jobs.
2. Run event hash-chain validation.
3. Identify missing/corrupt sequence and persistence backend status.
4. Restore from the latest trusted backup if corruption is confirmed.
5. Record incident evidence and restart only after validation passes.

Fail closed: no recovery from an invalid event chain.
