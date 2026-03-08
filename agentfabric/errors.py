"""Shared domain exceptions."""


class AgentFabricError(Exception):
    """Base class for platform errors."""


class AuthorizationError(AgentFabricError):
    """Raised when caller is not authorized."""


class ValidationError(AgentFabricError):
    """Raised when user input is invalid."""


class NotFoundError(AgentFabricError):
    """Raised when an entity cannot be found."""


class ConflictError(AgentFabricError):
    """Raised for uniqueness and lifecycle conflicts."""
