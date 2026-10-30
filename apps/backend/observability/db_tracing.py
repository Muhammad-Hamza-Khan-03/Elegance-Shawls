"""Database spans for SQLAlchemy engines. Records the operation (SELECT, INSERT, ...) only: never the
statement text or parameters, which can contain customer data."""
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from observability.tracing import get_tracer


def instrument_engine(engine: AsyncEngine) -> AsyncEngine:
    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _start(conn, cursor, statement, parameters, context, executemany):
        operation = (statement.lstrip().split(None, 1) or ["?"])[0].upper()[:12]
        # start_span (not start_as_current_span): it parents on the active request span and is ended by
        # the matching after/error event, which may run in a different greenlet context.
        started = get_tracer().start_span("db.query", attributes={"db.system": "postgresql", "db.operation": operation})
        conn.info.setdefault("_otel_spans", []).append(started)

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _end(conn, cursor, statement, parameters, context, executemany):
        if conn.info.get("_otel_spans"):
            conn.info["_otel_spans"].pop().end()

    @event.listens_for(sync_engine, "handle_error")
    def _error(exception_context):
        spans = exception_context.connection.info.get("_otel_spans") if exception_context.connection else None
        if spans:
            spans.pop().end()

    return engine
