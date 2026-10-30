"""PostgreSQL repositories for the catalogue, staged products and ingestion jobs.

Conventions:
* every function takes an AsyncSession and NEVER commits: the caller owns the transaction
  (`async with session.begin(): ...`), so a request or a job step is one atomic unit;
* multi-step operations run in a SAVEPOINT, so a failure undoes exactly that operation;
* no function publishes anything on its own: activating a product is an explicit call.
"""


class RepositoryError(Exception):
    pass


class NotFound(RepositoryError):
    pass


class Conflict(RepositoryError):
    """A uniqueness or workflow rule refused the change. `code` lets callers pick the API wording."""

    SLUG_EXISTS = "slug_exists"
    REVIEW_REQUIRED = "review_required"

    def __init__(self, message: str, code: str = "conflict"):
        super().__init__(message)
        self.code = code


class InvalidTransition(RepositoryError):
    def __init__(self, current: str, target: str):
        super().__init__(f"Cannot move a staged product from {current} to {target}")
        self.current, self.target = current, target


class InvalidDraft(RepositoryError):
    """The staged draft does not satisfy the catalogue's constraints."""


class ProductUnavailable(RepositoryError):
    """The catalogue product behind a staged product is missing or archived."""
