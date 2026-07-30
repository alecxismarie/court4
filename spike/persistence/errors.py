class PersistenceSpikeError(Exception):
    """Base deterministic domain error for the isolated persistence spike."""


class IdempotencyConflictError(PersistenceSpikeError):
    """An idempotency key was reused with a different request fingerprint."""


class OperationInProgressError(PersistenceSpikeError):
    """An equivalent operation exists but has not committed a result."""


class OwnershipMismatchError(PersistenceSpikeError):
    """A referenced resource is owned by another user."""


class ResourceNotFoundError(PersistenceSpikeError):
    """A spike resource does not exist."""


class InvalidStateTransitionError(PersistenceSpikeError):
    """The requested transition is not legal from the current state."""


class OptimisticConcurrencyError(PersistenceSpikeError):
    """The expected row version or state is stale."""


class BootstrapUserDisabledError(PersistenceSpikeError):
    """The temporary bootstrap identity is not explicitly allowed."""
