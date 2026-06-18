"""Built-in AgentFabric schema migrations."""

from importlib import import_module

from agentfabric.migrations.migration import Migration

initial = import_module("agentfabric.migrations.versions.0001_initial")

MIGRATIONS = [
    Migration(version=1, name="initial_generation4_collections", apply=initial.apply, validate=initial.validate),
]
