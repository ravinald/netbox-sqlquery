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

from .access import filter_abstract_schema
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


def _format_columns(columns):
    """Render a view's columns, annotating only jsonb columns (need special operators)."""
    parts = []
    for name, dtype in columns:
        if "json" in dtype:
            parts.append(f"{name} (jsonb)")
        else:
            parts.append(name)
    return ", ".join(parts)


def build_schema_text(user):
    """Build a compact schema description filtered to the user's permissions.

    Returns the schema as text suitable for inclusion in the LLM system prompt.
    """
    abstract_schema = get_abstract_schema()
    if not abstract_schema:
        return ""

    filtered = filter_abstract_schema(user, abstract_schema)

    lines = []
    for view_name, columns in sorted(filtered.items()):
        lines.append(f"Table: {view_name}")
        lines.append(f"Columns: {_format_columns(columns)}")
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


def load_config():
    """Load and validate the AI provider config. Returns (provider, config).

    Raises ValueError if the model is not configured. Shared by the one-shot
    generator and the agent loop.
    """
    provider = get_plugin_config("netbox_sqlquery", "ai_provider")
    model = get_plugin_config("netbox_sqlquery", "ai_model")
    if not model:
        raise ValueError("ai_model is not configured.")

    base_url = get_plugin_config("netbox_sqlquery", "ai_base_url")
    config = {
        "model": model,
        "base_url": base_url.rstrip("/") if base_url else "",
        "api_key": get_plugin_config("netbox_sqlquery", "ai_api_key"),
        "temperature": get_plugin_config("netbox_sqlquery", "ai_temperature"),
        "max_tokens": get_plugin_config("netbox_sqlquery", "ai_max_tokens"),
        "timeout": get_plugin_config("netbox_sqlquery", "ai_timeout"),
    }
    return provider, config


def domain_context_block():
    """Return the optional site-specific context, wrapped for prompt inclusion."""
    domain_context = get_plugin_config("netbox_sqlquery", "ai_system_context")
    if domain_context:
        return "\n" + domain_context.strip() + "\n"
    return ""


def generate_sql(natural_language, user):
    """Generate a SQL query from natural language using the configured LLM.

    One-shot text-to-SQL: the full permission-filtered schema goes in the system
    prompt and the model must emit valid SQL in a single turn. Kept as the fallback
    path; the agent loop in ``nl_agent`` is the default.

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

    provider, config = load_config()

    schema_text = build_schema_text(user)
    if not schema_text:
        raise ValueError("No accessible tables found for schema context.")

    system_prompt = SYSTEM_PROMPT.format(schema=schema_text, domain_context=domain_context_block())

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
    body = _http_post_raw(url, payload, headers, timeout)

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


def _http_post_raw(url, payload, headers, timeout=30):
    """POST JSON and return the parsed response body, with friendly error wrapping."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
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


# ---------------------------------------------------------------------------
# Tool-calling transport
#
# chat_with_tools() is provider-agnostic. The agent loop in nl_agent maintains a
# neutral message list and tool specs; these helpers translate to/from each
# provider's wire format and return a normalized assistant turn:
#
#     {"text": str | None, "tool_calls": [{"id", "name", "arguments": dict}, ...]}
#
# Neutral message shapes the loop produces:
#   {"role": "system"|"user", "content": str}
#   {"role": "assistant", "content": str | None, "tool_calls": [...]}
#   {"role": "tool", "tool_call_id": str, "name": str, "content": str}
# ---------------------------------------------------------------------------


def chat_with_tools(messages, tools, config, provider):
    """Run one chat turn with tool support. Returns a normalized assistant turn."""
    if provider == "anthropic":
        return _anthropic_chat(messages, tools, config)
    base_url = config["base_url"]
    if not base_url:
        raise ValueError("ai_base_url is required for the openai provider.")
    if ":11434" in base_url:
        return _ollama_chat(messages, tools, config)
    return _openai_chat(messages, tools, config)


def _openai_tools(tools):
    return [{"type": "function", "function": t} for t in tools]


def _openai_chat(messages, tools, config):
    wire = []
    for m in messages:
        role = m["role"]
        if role == "tool":
            wire.append(
                {"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]}
            )
        elif role == "assistant":
            calls = m.get("tool_calls") or []
            # OpenAI accepts null content only alongside tool_calls.
            content = m.get("content") or (None if calls else "")
            entry = {"role": "assistant", "content": content}
            if calls:
                entry["tool_calls"] = [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])},
                    }
                    for c in calls
                ]
            wire.append(entry)
        else:
            wire.append({"role": role, "content": m["content"]})

    payload = {
        "model": config["model"],
        "messages": wire,
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
        "tools": _openai_tools(tools),
        "tool_choice": "auto",
    }
    headers = {"Content-Type": "application/json"}
    if config["api_key"]:
        headers["Authorization"] = f"Bearer {config['api_key']}"

    body = _http_post_raw(
        f"{config['base_url']}/chat/completions", payload, headers, config["timeout"]
    )
    try:
        message = body["choices"][0]["message"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected OpenAI response: {json.dumps(body)[:500]}") from exc

    calls = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function", {})
        calls.append(
            {
                "id": tc.get("id") or f"call_{len(calls)}",
                "name": fn.get("name", ""),
                "arguments": _loads_args(fn.get("arguments")),
            }
        )
    return {"text": message.get("content"), "tool_calls": calls}


def _ollama_chat(messages, tools, config):
    base_url = config["base_url"].rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]

    wire = []
    for m in messages:
        role = m["role"]
        if role == "tool":
            wire.append({"role": "tool", "content": m["content"]})
        elif role == "assistant":
            entry = {"role": "assistant", "content": m.get("content") or ""}
            calls = m.get("tool_calls") or []
            if calls:
                entry["tool_calls"] = [
                    {"function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls
                ]
            wire.append(entry)
        else:
            wire.append({"role": role, "content": m["content"]})

    payload = {
        "model": config["model"],
        "messages": wire,
        "tools": _openai_tools(tools),
        "stream": False,
        "options": {"temperature": config["temperature"], "num_ctx": 8192},
    }
    headers = {"Content-Type": "application/json"}
    body = _http_post_raw(f"{base_url}/api/chat", payload, headers, config["timeout"])
    try:
        message = body["message"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"Unexpected Ollama response: {json.dumps(body)[:500]}") from exc

    calls = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function", {})
        args = fn.get("arguments")
        calls.append(
            {
                "id": f"call_{len(calls)}",
                "name": fn.get("name", ""),
                "arguments": args if isinstance(args, dict) else _loads_args(args),
            }
        )
    return {"text": message.get("content"), "tool_calls": calls}


def _anthropic_chat(messages, tools, config):
    api_key = config["api_key"]
    if not api_key:
        raise ValueError("ai_api_key is required for the anthropic provider.")

    system = ""
    wire = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system = m["content"]
        elif role == "user":
            wire.append({"role": "user", "content": m["content"]})
        elif role == "assistant":
            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for c in m.get("tool_calls") or []:
                blocks.append(
                    {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["arguments"]}
                )
            if not blocks:
                blocks.append({"type": "text", "text": ""})
            wire.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": m["tool_call_id"],
                "content": m["content"],
            }
            # Merge consecutive tool results into the same user turn.
            if wire and wire[-1]["role"] == "user" and isinstance(wire[-1]["content"], list):
                wire[-1]["content"].append(block)
            else:
                wire.append({"role": "user", "content": [block]})

    payload = {
        "model": config["model"],
        "max_tokens": config["max_tokens"],
        "system": system,
        "messages": wire,
        "temperature": config["temperature"],
        "tools": [
            {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
            for t in tools
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    base_url = config["base_url"] or "https://api.anthropic.com"
    body = _http_post_raw(f"{base_url}/v1/messages", payload, headers, config["timeout"])

    text_parts = []
    calls = []
    for block in body.get("content") or []:
        btype = block.get("type")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "tool_use":
            calls.append(
                {
                    "id": block.get("id"),
                    "name": block.get("name", ""),
                    "arguments": block.get("input") or {},
                }
            )
    if not body.get("content") and "error" not in body:
        raise RuntimeError(f"Unexpected Anthropic response: {json.dumps(body)[:500]}")
    return {"text": "".join(text_parts) or None, "tool_calls": calls}


def _loads_args(raw):
    """Parse a tool-call arguments string into a dict, tolerating junk."""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
