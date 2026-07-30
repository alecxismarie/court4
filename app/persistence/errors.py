"""Typed persistence failures safe for translation at API boundaries."""


class PersistenceError(RuntimeError):
    pass


class PersistenceConfigurationError(PersistenceError):
    pass


class PersistenceUnavailableError(PersistenceError):
    pass


class ResourceNotFoundError(PersistenceError):
    pass


class OwnershipMismatchError(PersistenceError):
    pass


class IdempotencyConflictError(PersistenceError):
    pass


class OperationInProgressError(PersistenceError):
    pass


class AnalysisAlreadyProcessingError(OperationInProgressError):
    pass


class OptimisticConcurrencyError(PersistenceError):
    pass


class InvalidStateTransitionError(PersistenceError):
    pass


class StaleRunConflictError(PersistenceError):
    pass


class ArtifactNotAvailableError(ResourceNotFoundError):
    pass


class MigrationDataInvalidError(PersistenceError):
    pass
