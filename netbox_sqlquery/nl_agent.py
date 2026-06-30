"""Tool-calling agent that turns natural language into SQL.

Replaces one-shot text-to-SQL (``llm.generate_sql``). Instead of dumping the whole
schema into a prompt and hoping the model writes valid SQL blind, the model drives a
small set of tools and gets execution feedback to self-correct:

- ``list_tables`` / ``describe_table`` -- pull schema on demand (permission-filtered)
- ``lookup_values`` -- resolve a literal against real column values (grounding)
- ``run_sql_dry`` -- execute a candidate read-only with a tiny LIMIT and see rows/errors
- ``submit_query`` -- hand back the final query (validated before acceptance)

Every tool that touches data routes through the same ``check_access`` +
``execute_read_query`` path as the rest of the plugin, so per-user permissions are
enforced on every step -- not just at the end.
"""

import logging
import re

from netbox.plugins import get_plugin_config

from . import llm
from .access import check_access, extract_tables, filter_abstract_schema
from .models import NLExample, SavedQuery
from .query import execute_read_query
from .schema import get_abstract_schema
from .sqlvalidate import is_read_only_select, unknown_columns

logger = logging.getLogger("netbox_sqlquery")

MAX_NL_INPUT_LENGTH = llm.MAX_NL_INPUT_LENGTH
_EXAMPLE_CANDIDATE_CAP = 200
_CELL_MAX = 60

AGENT_SYSTEM_PROMPT = """\
You convert natural language questions into a single PostgreSQL SELECT query against \
denormalized NetBox views (named nb_*).

Work iteratively using the tools provided. A good loop is:
1. Call list_tables to see which views you can access.
2. Call describe_table on the few views you need to learn their columns.
3. If the question names a specific value (a site, manufacturer, role, tenant, ...), \
call lookup_values to find how it is actually spelled in the data.
4. Call run_sql_dry to test your query and read the sample rows or the error.
5. When the query is correct, call submit_query with the final SQL.

Rules for the SQL:
- These are DENORMALIZED VIEWS. Relationship columns already contain resolved text \
names: "tenant" holds the tenant name, "site" holds the site name, etc. Most questions \
need ONE view with WHERE clauses. Do NOT join unless you truly need columns from \
multiple views, and never join on id columns.
- "tags" is comma-separated text. Filter with tags ILIKE '%mytag%'. Never use JSON \
operators on tags.
- "custom_field_data" is jsonb. Use -> and ->> and guard against nulls.
- When matching text (name, description, comments, dns_name), replace spaces in the \
search term with % so each word matches independently: "load balancer" -> \
ILIKE '%load%balancer%'.
- nb_vm_interfaces is for virtual machine interfaces; nb_interfaces is physical only.
- One SELECT statement, no trailing semicolon, no DML/DDL.
{domain_context}{examples}"""

TOOL_SPECS = [
    {
        "name": "list_tables",
        "description": "List the nb_* views you are allowed to query.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "describe_table",
        "description": "Show the columns (and jsonb annotations) of one nb_* view.",
        "parameters": {
            "type": "object",
            "properties": {"table": {"type": "string", "description": "An nb_* view name."}},
            "required": ["table"],
        },
    },
    {
        "name": "lookup_values",
        "description": (
            "Find real distinct values in a column that match a search term. Use this to "
            "discover how a name/label is actually spelled before filtering on it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "table": {"type": "string"},
                "column": {"type": "string"},
                "search": {"type": "string", "description": "Substring to search for."},
            },
            "required": ["table", "column", "search"],
        },
    },
    {
        "name": "run_sql_dry",
        "description": (
            "Run a candidate SELECT read-only with a small LIMIT and return rows or the error."
        ),
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
        },
    },
    {
        "name": "submit_query",
        "description": "Submit the final SELECT query as your answer.",
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
        },
    },
]


def generate_sql_agentic(natural_language, user):
    """Drive the tool-calling loop and return a validated SQL string.

    Raises ValueError on bad input/config and RuntimeError if the model fails to
    produce a valid query within ``ai_max_iterations`` steps.
    """
    if len(natural_language) > MAX_NL_INPUT_LENGTH:
        raise ValueError(f"Input exceeds maximum length of {MAX_NL_INPUT_LENGTH} characters.")

    provider, config = llm.load_config()

    schema = _filtered_schema(user)
    if not schema:
        raise ValueError("No accessible tables found for schema context.")

    max_iterations = get_plugin_config("netbox_sqlquery", "ai_max_iterations")

    messages = [
        {"role": "system", "content": _build_system_prompt(user, natural_language)},
        {"role": "user", "content": natural_language},
    ]

    last_candidate = None
    for _ in range(max_iterations):
        turn = llm.chat_with_tools(messages, TOOL_SPECS, config, provider)
        tool_calls = turn.get("tool_calls") or []
        messages.append(
            {"role": "assistant", "content": turn.get("text"), "tool_calls": tool_calls}
        )

        if not tool_calls:
            candidate = llm._sanitize_sql(turn.get("text") or "")
            err = _validate_candidate(user, schema, candidate)
            if err is None:
                return candidate
            if candidate:
                last_candidate = candidate
            messages.append(
                {
                    "role": "user",
                    "content": f"That is not usable yet: {err} "
                    "Call submit_query with a corrected SELECT.",
                }
            )
            continue

        accepted = None
        for call in tool_calls:
            name = call.get("name", "")
            args = call.get("arguments") or {}
            if name == "submit_query":
                candidate = llm._sanitize_sql(args.get("sql", "") or "")
                err = _validate_candidate(user, schema, candidate)
                if err is None:
                    accepted = candidate
                    content = "Accepted."
                else:
                    if candidate:
                        last_candidate = candidate
                    content = f"Rejected: {err}"
            else:
                content = _dispatch_tool(name, args, user, schema)
            messages.append(
                {"role": "tool", "tool_call_id": call.get("id"), "name": name, "content": content}
            )

        if accepted:
            return accepted

    if last_candidate and _validate_candidate(user, schema, last_candidate) is None:
        return last_candidate
    raise RuntimeError("The AI did not produce a valid query within the allotted steps.")


def record_example(user, question, sql):
    """Persist an accepted NL->SQL pair for future few-shot retrieval. Best-effort."""
    question = (question or "").strip()
    sql = (sql or "").strip()
    if not question or not sql:
        return
    try:
        NLExample.objects.create(question=question[:MAX_NL_INPUT_LENGTH], sql=sql, owner=user)
    except Exception as exc:  # pragma: no cover - never break the request over an example
        logger.debug("Could not record NL example: %s", exc)


# --- tool dispatch (the permission boundary) --------------------------------


def _dispatch_tool(name, args, user, schema):
    if name == "list_tables":
        return _tool_list_tables(schema)
    if name == "describe_table":
        return _tool_describe_table(schema, args.get("table", ""))
    if name == "lookup_values":
        return _tool_lookup_values(user, schema, args)
    if name == "run_sql_dry":
        return _tool_run_sql_dry(user, schema, args.get("sql", ""))
    return f"Unknown tool: {name}"


def _tool_list_tables(schema):
    if not schema:
        return "You have no accessible views."
    return "Accessible views:\n" + "\n".join(sorted(schema))


def _tool_describe_table(schema, table):
    table = (table or "").strip()
    if table not in schema:
        return f"Unknown or inaccessible view: {table!r}. Call list_tables first."
    return f"{table} columns: {llm._format_columns(schema[table])}"


def _tool_lookup_values(user, schema, args):
    table = (args.get("table") or "").strip()
    column = (args.get("column") or "").strip()
    search = (args.get("search") or "").strip()

    if table not in schema:
        return f"Unknown or inaccessible view: {table!r}. Call list_tables first."
    valid_columns = {col for col, _dtype in schema[table]}
    if column not in valid_columns:
        return f"Unknown column {column!r} on {table}. Call describe_table {table}."

    # Identifiers are whitelisted above; the search term is stripped of wildcards,
    # quotes, and backslashes before being embedded.
    safe = re.sub(r"[%_\\']", "", search)
    pattern = f"%{safe}%"
    sql = (
        f'SELECT DISTINCT "{column}"::text AS value FROM "{table}" '
        f'WHERE "{column}" IS NOT NULL AND "{column}"::text ILIKE \'{pattern}\' '
        "ORDER BY 1 LIMIT 25"
    )

    denied = check_access(user, extract_tables(sql))
    if denied:
        return f"Access denied to: {', '.join(sorted(denied))}"

    result = execute_read_query(sql, max_rows=25)
    if result["error"]:
        return f"Lookup error: {result['error']}"
    if not result["rows"]:
        return f"No values in {table}.{column} match {search!r}."
    values = [str(r[0]) for r in result["rows"]]
    return f"Matching values in {table}.{column}: " + ", ".join(values)


def _tool_run_sql_dry(user, schema, sql):
    sql = llm._sanitize_sql(sql or "")
    if not sql:
        return "No SQL provided."
    if not is_read_only_select(sql):
        return "Only a single read-only SELECT/WITH statement is allowed."

    denied = check_access(user, extract_tables(sql))
    if denied:
        return f"Access denied to: {', '.join(sorted(denied))}"

    warning = ""
    unknown = unknown_columns(sql, schema)
    if unknown:
        warning = f"Warning: unknown columns {', '.join(unknown)}. "

    limit = get_plugin_config("netbox_sqlquery", "ai_dry_run_limit")
    result = execute_read_query(sql, max_rows=limit)
    if result["error"]:
        return f"{warning}SQL error: {result['error']}"
    return warning + _format_rows(result["columns"], result["rows"], result["truncated"])


# --- validation, schema, prompt helpers -------------------------------------


def _validate_candidate(user, schema, sql):
    """Return an error string if *sql* is unusable, else None."""
    if not sql:
        return "no query was provided."
    if not is_read_only_select(sql):
        return "it must be a single read-only SELECT/WITH statement."
    denied = check_access(user, extract_tables(sql))
    if denied:
        return f"access denied to: {', '.join(sorted(denied))}."
    unknown = unknown_columns(sql, schema)
    if unknown:
        return f"these columns do not exist: {', '.join(unknown)}. Use describe_table to check."
    return None


def _filtered_schema(user):
    abstract_schema = get_abstract_schema()
    if not abstract_schema:
        return {}
    return filter_abstract_schema(user, abstract_schema)


def _build_system_prompt(user, question):
    examples = _format_examples(_retrieve_examples(user, question))
    return AGENT_SYSTEM_PROMPT.format(
        domain_context=llm.domain_context_block(),
        examples=examples,
    )


def _format_rows(columns, rows, truncated):
    if not columns:
        return "Query ran but returned no columns."
    lines = [" | ".join(columns)]
    for row in rows:
        cells = []
        for cell in row:
            text = "NULL" if cell is None else str(cell)
            if len(text) > _CELL_MAX:
                text = text[: _CELL_MAX - 1] + "…"
            cells.append(text)
        lines.append(" | ".join(cells))
    note = f"\n({len(rows)} sample row(s)"
    note += ", more available)" if truncated else ")"
    return "\n".join(lines) + note


# --- few-shot retrieval -----------------------------------------------------


def _tokens(text):
    return set(re.findall(r"[a-z0-9_]+", (text or "").lower()))


def _similarity(query_tokens, text):
    other = _tokens(text)
    if not other:
        return 0.0
    return len(query_tokens & other) / len(query_tokens | other)


def _retrieve_examples(user, question):
    """Return up to ai_fewshot_k (question, sql) pairs relevant to *question*.

    Sourced from the user's visible saved queries and accepted NL examples, and
    filtered so every example only references tables the user may query.
    """
    k = get_plugin_config("netbox_sqlquery", "ai_fewshot_k")
    if not k:
        return []

    candidates = []
    try:
        for sq in SavedQuery.visible_to(user)[:_EXAMPLE_CANDIDATE_CAP]:
            label = sq.name if not sq.description else f"{sq.name}: {sq.description}"
            candidates.append((label, sq.sql))
        for ex in NLExample.objects.all()[:_EXAMPLE_CANDIDATE_CAP]:
            candidates.append((ex.question, ex.sql))
    except Exception as exc:  # pragma: no cover - retrieval is best-effort
        logger.debug("Few-shot retrieval failed: %s", exc)
        return []

    query_tokens = _tokens(question)
    if not query_tokens:
        return []

    scored = []
    for text, sql in candidates:
        if not sql or not is_read_only_select(sql):
            continue
        if check_access(user, extract_tables(sql)):
            continue  # references a table this user cannot query
        score = _similarity(query_tokens, text)
        if score > 0:
            scored.append((score, text, sql))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [(text, sql) for _score, text, sql in scored[:k]]


def _format_examples(examples):
    if not examples:
        return ""
    blocks = ["\nExamples of good queries for this database:"]
    for text, sql in examples:
        blocks.append(f"-- {text}\n{sql}")
    return "\n".join(blocks) + "\n"
