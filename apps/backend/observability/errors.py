"""Privacy-safe application error capture (issue #146).

The reporter is a no-op until one is installed with ``set_reporter``; no provider
is chosen here. Reports carry only identifiers: never the exception message,
headers, query string, body or tokens, because those can hold personal data.
"""
import logging
import os
from typing import Callable

logger = logging.getLogger("elegance.errors")

Reporter = Callable[[dict], None]
_reporter: Reporter | None = None


def set_reporter(reporter: Reporter | None) -> None:
    global _reporter
    _reporter = reporter


def capture_exception(exc: BaseException, *, request_id: str, route: str, status: int = 500) -> None:
    if _reporter is None:
        return
    try:
        _reporter({
            "request_id": request_id,
            "route": route,
            "status": status,
            "exception_type": type(exc).__name__,
            "release": os.environ.get("RELEASE_SHA", "unknown"),
        })
    except Exception:  # a broken reporter must never change the response
        logger.warning("error reporter failed", exc_info=False)
