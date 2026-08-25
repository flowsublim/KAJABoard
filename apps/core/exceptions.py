class AuditEventImmutableError(RuntimeError):
    """Raised when ordinary application code attempts to mutate audit history."""


class IdempotencyConflictError(RuntimeError):
    """Raised when one idempotency key is reused for a different request."""


class IdempotencyStateError(RuntimeError):
    """Raised when an idempotency record receives an illegal state transition."""


class PostedRecordImmutableError(RuntimeError):
    """Raised when a posted/reversed record is sent through an edit path."""
