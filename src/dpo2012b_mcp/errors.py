class ScopeError(RuntimeError):
    """Base exception for scope communication failures."""


class ScopeNotConnectedError(ScopeError):
    """Raised when a tool requires an active scope connection."""


class UnsafeCommandError(ScopeError):
    """Raised when a potentially destructive SCPI command is blocked."""

