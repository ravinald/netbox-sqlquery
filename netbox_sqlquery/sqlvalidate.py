"""Deterministic SQL guards backed by sqlglot.

Replaces the fragile string/regex checks with an AST. Three jobs:

- ``is_read_only_select`` -- prove a statement is a single read-only SELECT/WITH
  (catches multi-statement payloads and data-modifying CTEs that prefix checks miss).
- ``statement_tables`` -- pull referenced table names from the parse tree.
- ``unknown_columns`` -- flag hallucinated columns against the known schema, used by
  the agent loop to self-correct before execution.

Every function degrades gracefully if sqlglot is unavailable or the SQL fails to
parse, so the plugin never hard-fails on this layer -- the read-only transaction in
``query.execute_read_query`` remains the ultimate backstop.
"""

import logging

logger = logging.getLogger("netbox_sqlquery")

try:
    import sqlglot
    from sqlglot import exp

    SQLGLOT_AVAILABLE = True
except ImportError:  # pragma: no cover - sqlglot is a declared dependency
    SQLGLOT_AVAILABLE = False

DIALECT = "postgres"

# Statement node types that must never appear anywhere in a read-only query,
# including inside CTEs (Postgres allows data-modifying CTEs).
_FORBIDDEN_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Create",
    "Drop",
    "Alter",
    "TruncateTable",
    "Command",  # anything sqlglot can't model: VACUUM, CALL, DO, COPY, ...
    "Set",
)


def _forbidden_types():
    return tuple(getattr(exp, name) for name in _FORBIDDEN_NAMES if hasattr(exp, name))


def _parse_one(sql):
    """Parse a single statement. Returns the root expression or None.

    Returns None if sqlglot is missing, the SQL is empty/unparseable, or the input
    contains more than one statement.
    """
    if not SQLGLOT_AVAILABLE or not sql or not sql.strip():
        return None
    try:
        statements = sqlglot.parse(sql, read=DIALECT)
    except Exception as exc:
        logger.debug("sqlglot failed to parse: %s", exc)
        return None
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return None
    return statements[0]


def is_read_only_select(sql):
    """Return True only if *sql* is provably a single read-only SELECT/WITH.

    When sqlglot is unavailable, fall back to a conservative prefix check so the
    feature keeps working without the dependency.
    """
    if not SQLGLOT_AVAILABLE:
        normalized = (sql or "").lstrip().upper()
        return normalized.startswith("SELECT") or normalized.startswith("WITH")

    root = _parse_one(sql)
    if root is None:
        return False

    if root.find(*_forbidden_types()):
        return False

    # Accept any read query: SELECT, set operations (UNION/EXCEPT/INTERSECT),
    # and CTE-wrapped queries. sqlglot >=25 models these under exp.Query.
    query_base = getattr(exp, "Query", None)
    if query_base is not None and isinstance(root, query_base):
        return True
    return isinstance(root, exp.Select | exp.Subquery)


def statement_tables(sql):
    """Return the set of table names referenced in *sql*, or None on parse failure.

    Includes CTE names and subquery sources (matching the legacy regex behaviour),
    so callers expand abstract views and run access checks the same way as before.
    Returns None to signal the caller should fall back to its own extraction.
    """
    root = _parse_one(sql)
    if root is None:
        return None
    return {t.name for t in root.find_all(exp.Table) if t.name}


def _schema_columns(schema):
    """Build {table: set(columns)} from a {table: [(col, type), ...]} schema map."""
    out = {}
    for table, columns in schema.items():
        out[table] = {col for col, _dtype in columns}
    return out


def unknown_columns(sql, schema):
    """Return columns referenced in *sql* that do not exist in *schema*.

    Conservative by design -- only flags a column when its table resolves to a known
    schema table. Unqualified columns are checked only when exactly one referenced
    table is in the schema; anything ambiguous (CTEs, subquery aliases, unknown
    tables) is skipped to avoid false rejections of valid SQL.
    """
    root = _parse_one(sql)
    if root is None or not schema:
        return []

    cols_by_table = _schema_columns(schema)

    # alias_or_name -> real table name, for tables we can see in the schema.
    alias_to_table = {}
    schema_sources = set()
    table_nodes = list(root.find_all(exp.Table))
    for tbl in table_nodes:
        if tbl.name in cols_by_table:
            alias_to_table[tbl.alias_or_name] = tbl.name
            schema_sources.add(tbl.name)

    if not schema_sources:
        return []

    # Only resolve UNqualified columns when the statement is a single-table query
    # with no CTEs -- otherwise an outer column may belong to a CTE/subquery scope
    # we can't see, and we'd flag a valid column.
    has_cte = root.find(exp.CTE) is not None
    simple = not has_cte and len(table_nodes) == 1 and len(schema_sources) == 1
    sole_source = next(iter(schema_sources)) if simple else None

    unknown = set()
    for col in root.find_all(exp.Column):
        qualifier = col.table
        if qualifier:
            real = alias_to_table.get(qualifier)
            if real is None:
                continue  # qualifier points at a CTE/subquery/unknown table
        elif sole_source is not None:
            real = sole_source
        else:
            continue  # unqualified column we can't safely resolve -- skip

        if col.name and col.name not in cols_by_table[real]:
            unknown.add(f"{real}.{col.name}")

    return sorted(unknown)
