# Governance Demo

The pilot flow creates a governance organization, review team, and charter for `demo-tenant`.

`scripts/run_demo_pilot.py` creates a proposal for a governed workflow execution, casts an approval vote, executes the approved action, and stores a decision record.

The workflow itself also demonstrates a human approval pause and resume through a task node that requires approval before compliance review can continue.
