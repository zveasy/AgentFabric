# Reference Agents

Generation 11 ships seven local-mode reference agents:

- `ResearchAgent`: gathers safe research context.
- `DocumentAnalysisAgent`: extracts obligations from VEIL-referenced documents.
- `ComplianceReviewAgent`: reviews workflow evidence.
- `CodeReviewAgent`: reviews VEIL-referenced diffs.
- `WorkflowPlannerAgent`: creates governed task plans.
- `HumanApprovalAgent`: bridges workflows to human decisions.
- `MarketplaceVerifierAgent`: verifies signed package fixtures and risk summaries.

Each agent is defined in `agentfabric/reference_agents/agents.py` with capabilities, tool permissions, example inputs and outputs, and marketplace package metadata.
