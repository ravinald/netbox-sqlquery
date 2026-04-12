"""LLM integration for natural language to SQL generation.

Supports two provider types:
- "openai": OpenAI-compatible APIs (Ollama, OpenAI, vLLM, etc.)
- "anthropic": Anthropic Claude API
"""

import json
import logging
import re
import socket
import urllib.error
import urllib.request

from netbox.plugins import get_plugin_config

from .abstract_schema import ABSTRACT_TO_TABLES
from .access import ALL_TABLES, _allowed_tables, _hard_denies_set
from .schema import get_abstract_schema

logger = logging.getLogger("netbox_sqlquery")

MAX_NL_INPUT_LENGTH = 2000

SYSTEM_PROMPT = """\
You are a SQL query generator for a PostgreSQL database. Return ONLY the \
raw SQL query. No explanations, no markdown, no comments, no preamble. \
One SELECT statement only, no trailing semicolon.

CRITICAL: These are DENORMALIZED VIEWS. Each view already contains \
resolved text values for all relationships. The "tenant" column contains \
the tenant NAME (text), "site" contains the site NAME (text), etc. \
Most queries need only ONE table with WHERE clauses. DO NOT JOIN tables \
unless you truly need columns from multiple views. Never join on ID \
columns -- all relationship columns are already text names.

Column types:
- "tags" = comma-separated text (e.g., "tag1, tag2"). Filter with: \
tags ILIKE '%mytag%'. NEVER use JSON operators on tags.
- "custom_field_data" = jsonb containing all custom fields. Access \
nested values with -> and ->>. Always guard against nulls: \
custom_field_data->'key' IS NOT NULL AND custom_field_data->>'key' = 'val'
- When searching text fields (description, name, comments, dns_name), \
replace spaces in search terms with % wildcards so each word matches \
independently. Example: "load balancer" becomes ILIKE '%load%balancer%'. \
This matches "load_balancer", "load-balancer", "Load Balancer", etc.
- nb_vm_interfaces is for virtual machine interfaces (has virtual_machine \
column). nb_interfaces is for physical device interfaces only.
{domain_context}
Available tables and columns:

{schema}"""


def build_schema_text(user):
    """Build a compact schema description filtered to the user's permissions.

    Returns the schema as text suitable for inclusion in the LLM system prompt.
    """
    abstract_schema = get_abstract_schema()
    if not abstract_schema:
        return ""

    allowed = _allowed_tables(user)
    denied = _hard_denies_set()

    lines = []
    for view_name, columns in sorted(abstract_schema.items()):
        # Check if the user can access the underlying tables for this view
        underlying = ABSTRACT_TO_TABLES.get(view_name, set())
        if underlying:
            if allowed is not ALL_TABLES:
                if not underlying.issubset(allowed):
                    continue
            if underlying & denied:
                continue

        col_parts = []
        for name, dtype in columns:
            # Only annotate type for jsonb columns (need special operators)
            if "json" in dtype:
                col_parts.append(f"{name} (jsonb)")
            else:
                col_parts.append(name)
        lines.append(f"Table: {view_name}")
        lines.append(f"Columns: {', '.join(col_parts)}")
        lines.append("")

    return "\n".join(lines)


def _sanitize_sql(raw):
    """Clean LLM output to extract a single SQL statement.

    - Extracts SQL from markdown code fences if present
    - Finds the first SELECT/WITH statement even if preceded by text
    - Takes only the first statement (before any semicolon)
    - Strips whitespace
    """
    sql = raw.strip()

    # Extract content from markdown code fences if present
    fence_match = re.search(r"```(?:\w*)\s*\n?(.*?)```", sql, re.DOTALL)
    if fence_match:
        sql = fence_match.group(1).strip()
    else:
        # No fences -- find the first SELECT or WITH keyword
        stmt_match = re.search(r"\b(SELECT\b.*|WITH\b.*)", sql, re.IGNORECASE | re.DOTALL)
        if stmt_match:
            sql = stmt_match.group(1).strip()

    # Take only the first statement to prevent multi-statement injection
    first_stmt = sql.split(";")[0].strip()

    return first_stmt


def generate_sql(natural_language, user):
    """Generate a SQL query from natural language using the configured LLM.

    Args:
        natural_language: The user's natural language query.
        user: The Django user object (for schema filtering).

    Returns:
        The generated SQL string, sanitized.

    Raises:
        ValueError: If configuration is incomplete or input is invalid.
        RuntimeError: If the LLM call fails.
    """
    if len(natural_language) > MAX_NL_INPUT_LENGTH:
        raise ValueError(f"Input exceeds maximum length of {MAX_NL_INPUT_LENGTH} characters.")

    provider = get_plugin_config("netbox_sqlquery", "ai_provider")
    model = get_plugin_config("netbox_sqlquery", "ai_model")
    base_url = get_plugin_config("netbox_sqlquery", "ai_base_url")
    api_key = get_plugin_config("netbox_sqlquery", "ai_api_key")
    temperature = get_plugin_config("netbox_sqlquery", "ai_temperature")
    max_tokens = get_plugin_config("netbox_sqlquery", "ai_max_tokens")

    if not model:
        raise ValueError("ai_model is not configured.")

    schema_text = build_schema_text(user)
    if not schema_text:
        raise ValueError("No accessible tables found for schema context.")

    domain_context = get_plugin_config("netbox_sqlquery", "ai_system_context")
    if domain_context:
        domain_context = "\n" + domain_context.strip() + "\n"
    else:
        domain_context = ""

    system_prompt = SYSTEM_PROMPT.format(schema=schema_text, domain_context=domain_context)

    timeout = get_plugin_config("netbox_sqlquery", "ai_timeout")

    config = {
        "model": model,
        "base_url": base_url.rstrip("/") if base_url else "",
        "api_key": api_key,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
    }

    if provider == "anthropic":
        raw_sql = _call_anthropic(system_prompt, natural_language, config)
    else:
        raw_sql = _call_openai_compatible(system_prompt, natural_language, config)

    return _sanitize_sql(raw_sql)


def _call_openai_compatible(system_prompt, user_message, config):
    """Call an OpenAI-compatible chat completions API.

    Works with Ollama, OpenAI, vLLM, and other compatible providers.
    Detects Ollama by base_url port and uses the native API for
    proper num_ctx support.
    """
    base_url = config["base_url"]
    if not base_url:
        raise ValueError("ai_base_url is required for the openai provider.")

    # Detect Ollama and use native /api/chat for num_ctx support
    if ":11434" in base_url:
        return _call_ollama_native(system_prompt, user_message, config)

    url = f"{base_url}/chat/completions"
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
    }

    headers = {"Content-Type": "application/json"}
    if config["api_key"]:
        headers["Authorization"] = f"Bearer {config['api_key']}"

    return _http_post(url, payload, headers, extract_openai=True, timeout=config["timeout"])


def _call_ollama_native(system_prompt, user_message, config):
    """Call Ollama's native /api/chat endpoint.

    Uses the native API instead of the OpenAI-compat layer so that
    options like num_ctx are properly respected.
    """
    # Strip /v1 suffix if present to get the Ollama base URL
    base_url = config["base_url"].rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]

    url = f"{base_url}/api/chat"
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "options": {
            "temperature": config["temperature"],
            "num_ctx": 8192,
        },
        "stream": False,
    }

    headers = {"Content-Type": "application/json"}

    return _http_post(url, payload, headers, extract_ollama=True, timeout=config["timeout"])


def _call_anthropic(system_prompt, user_message, config):
    """Call the Anthropic Messages API."""
    api_key = config["api_key"]
    if not api_key:
        raise ValueError("ai_api_key is required for the anthropic provider.")

    base_url = config["base_url"] or "https://api.anthropic.com"
    url = f"{base_url}/v1/messages"
    payload = {
        "model": config["model"],
        "max_tokens": config["max_tokens"],
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_message},
        ],
        "temperature": config["temperature"],
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    return _http_post(url, payload, headers, extract_openai=False, timeout=config["timeout"])


def _http_post(
    url,
    payload,
    headers,
    extract_openai=True,
    extract_ollama=False,
    timeout=30,
):
    """Make an HTTP POST request and extract the response text.

    Args:
        url: The endpoint URL.
        payload: The JSON request body.
        headers: HTTP headers dict.
        extract_openai: If True, extract from OpenAI format.
        extract_ollama: If True, extract from Ollama native format.
        timeout: Request timeout in seconds.

    Returns:
        The extracted text content from the response.

    Raises:
        RuntimeError: On HTTP errors or unexpected response format.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        msg = (
            f"LLM request timed out after {timeout}s."
            " The model may be loading or the server may be unreachable."
        )
        raise RuntimeError(msg) from exc
    except urllib.error.HTTPError as exc:
        error_body = ""
        try:
            error_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"LLM API returned HTTP {exc.code}: {error_body[:500]}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, socket.timeout):
            msg = (
                f"LLM connection timed out after {timeout}s."
                " Check that the LLM service is reachable."
            )
            raise RuntimeError(msg) from exc
        raise RuntimeError(f"Failed to connect to LLM API: {exc.reason}") from exc

    if extract_ollama:
        # Ollama native: {"message": {"content": "..."}}
        try:
            return body["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Ollama response: {json.dumps(body)[:500]}") from exc
    elif extract_openai:
        # OpenAI format: {"choices": [{"message": {"content": "..."}}]}
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected OpenAI response: {json.dumps(body)[:500]}") from exc
    else:
        # Anthropic format: {"content": [{"type": "text", "text": "..."}]}
        try:
            return body["content"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected Anthropic response: {json.dumps(body)[:500]}") from exc
