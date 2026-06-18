"""Production API server package."""


def create_app(*args, **kwargs):
    """Import the application lazily to keep server configuration importable."""
    from agentfabric.server.app import create_app as application_factory

    return application_factory(*args, **kwargs)

__all__ = ["create_app"]
