from __future__ import annotations

import unittest

from agentfabric.errors import AuthorizationError
from agentfabric.phase3.collaboration import CollaborationOrchestrator, CollaborationPolicy
from agentfabric.phase3.protocol import CollaborationMessage, TraceContext
from agentfabric.phase3.workflow import WorkflowEngine, WorkflowNode


class Phase3CollaborationTests(unittest.TestCase):
    def test_delegation_policy_and_quota(self) -> None:
        policy = CollaborationPolicy(max_delegations_per_run=1)
        orchestrator = CollaborationOrchestrator(policy)
        orchestrator.allow_edge("research", "financial")
        message = CollaborationMessage(
            message_type="delegate",
            source_agent="research",
            target_agent="financial",
            payload={"ticker": "AAPL"},
            trace=TraceContext(correlation_id="corr-1"),
        )
        first = orchestrator.delegate(message, lambda m: {"ok": m.payload["ticker"]})
        self.assertEqual(first["result"]["ok"], "AAPL")
        with self.assertRaises(AuthorizationError):
            orchestrator.delegate(message, lambda m: {"ok": True})

    def test_workflow_retries_and_idempotency_cache(self) -> None:
        engine = WorkflowEngine()
        nodes = [
            WorkflowNode(node_id="research", agent_name="research-agent"),
            WorkflowNode(node_id="strategy", agent_name="strategy-agent", dependencies=("research",), max_retries=1),
        ]
        attempts = {"strategy": 0}

        def runner(node: WorkflowNode, payload: dict) -> dict:
            if node.node_id == "strategy":
                attempts["strategy"] += 1
                if attempts["strategy"] == 1:
                    raise RuntimeError("transient")
            return {"node": node.node_id, "deps": payload["dependency_results"]}

        result = engine.run(
            workflow_id="wf-1",
            idempotency_key="idem-1",
            nodes=nodes,
            initial_payload={"request": "build thesis"},
            node_runner=runner,
        )
        cached = engine.run(
            workflow_id="wf-1",
            idempotency_key="idem-1",
            nodes=nodes,
            initial_payload={"request": "build thesis"},
            node_runner=runner,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(cached, result)
        self.assertEqual(attempts["strategy"], 2)


if __name__ == "__main__":
    unittest.main()
