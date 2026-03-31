"""Shared query execution functions used by both the web UI and API."""

from django.db import DatabaseError, connection, transaction
from netbox.plugins import get_plugin_config


class _ReadOnlyRollback(Exception):
    """Raised to force rollback of the read-only transaction."""


def execute_read_query(sql, timeout_ms=None, max_rows=None):
    """Execute a read-only SQL query.

    Returns dict with keys: columns, rows, row_count, truncated, error.
    """
    if timeout_ms is None:
        timeout_ms = get_plugin_config("netbox_sqlquery", "statement_timeout_ms")
    if max_rows is None:
        max_rows = get_plugin_config("netbox_sqlquery", "max_rows")

    result = {"columns": [], "rows": [], "row_count": 0, "truncated": False, "error": None}

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(f"SET LOCAL statement_timeout = '{timeout_ms}'")
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute(sql)
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchmany(max_rows + 1)
            raise _ReadOnlyRollback()
    except _ReadOnlyRollback:
        truncated = len(rows) > max_rows
        if truncated:
            rows = rows[:max_rows]
        result.update(
            columns=columns,
            rows=[list(r) for r in rows],
            row_count=len(rows),
            truncated=truncated,
        )
    except DatabaseError as exc:
        result["error"] = str(exc)

    return result


def execute_write_query(sql, timeout_ms=None, max_rows=None):
    """Execute a write SQL query (INSERT/UPDATE/DELETE).

    Returns dict with keys: columns, rows, row_count, rows_affected, error.
    """
    if timeout_ms is None:
        timeout_ms = get_plugin_config("netbox_sqlquery", "statement_timeout_ms")
    if max_rows is None:
        max_rows = get_plugin_config("netbox_sqlquery", "max_rows")

    result = {
        "columns": [],
        "rows": [],
        "row_count": 0,
        "rows_affected": 0,
        "error": None,
    }

    try:
        exec_sql = sql
        has_returning = "RETURNING" in sql.upper()
        normalized = sql.lstrip().upper()
        if not has_returning and (
            normalized.startswith("UPDATE") or normalized.startswith("DELETE")
        ):
            exec_sql = sql.rstrip().rstrip(";") + " RETURNING *"

        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL statement_timeout = '{timeout_ms}'")
            cursor.execute(exec_sql)
            rows_affected = cursor.rowcount

            if cursor.description:
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchmany(max_rows)
                result.update(
                    columns=columns,
                    rows=[list(r) for r in rows],
                    row_count=len(rows),
                )

        result["rows_affected"] = rows_affected
    except DatabaseError as exc:
        result["error"] = str(exc)

    return result


def is_write_query(sql):
    """Check if a SQL statement is a write query."""
    normalized = sql.lstrip().upper()
    return (
        normalized.startswith("INSERT")
        or normalized.startswith("UPDATE")
        or normalized.startswith("DELETE")
    )


def is_allowed_query(sql):
    """Check if a SQL statement type is permitted."""
    normalized = sql.lstrip().upper()
    return (
        normalized.startswith("SELECT")
        or normalized.startswith("WITH")
        or normalized.startswith("INSERT")
        or normalized.startswith("UPDATE")
        or normalized.startswith("DELETE")
    )
