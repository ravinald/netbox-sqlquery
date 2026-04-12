# Changelog - 2026-04-08

## Feature: Natural Language to SQL (AI Query)

Added LLM-powered natural language query support. Users can type plain English
questions in the SQL editor and the plugin will generate and execute SQL queries
using a configured LLM backend.

### New files
- `netbox_sqlquery/llm.py` - LLM provider abstraction supporting OpenAI-compatible
  APIs (Ollama, OpenAI, vLLM) and Anthropic Claude. Handles schema context building,
  prompt construction, provider dispatch, and output sanitization.
- `scripts/setup_ollama.sh` - Installation script for Ollama on Linux with
  multi-model support for A/B testing (qwen2.5-coder:7b, llama3.1:8b, codellama:7b).

### Modified files
- `netbox_sqlquery/__init__.py` - Added `ai_*` configuration keys to `default_settings`:
  `ai_enabled`, `ai_provider`, `ai_model`, `ai_base_url`, `ai_api_key`,
  `ai_temperature`, `ai_max_tokens`.
- `netbox_sqlquery/views.py` - Added `NLQueryAjaxView` AJAX endpoint for AI query
  processing. Added `ai_enabled` to template context.
- `netbox_sqlquery/urls.py` - Added `ajax/ai-query/` URL pattern.
- `netbox_sqlquery/templates/netbox_sqlquery/query.html` - Added `ai_enabled` to
  JS flags, AI button styling (purple tint, pulse animation), error/results containers.
- `netbox_sqlquery/static/netbox_sqlquery/editor.js` - Added SQL detection
  (`looksLikeSQL`), dynamic button text ("Run SQL query" / "Run AI query"),
  `runAIQuery()` AJAX handler, client-side `renderResults()`, `showError()`.

### UX behavior
- The submit button dynamically switches between "Run SQL query" (blue) and
  "Run AI query" (purple) based on whether the input looks like SQL.
- When AI returns results, the generated SQL replaces the editor content,
  flipping the button back to "Run SQL query" so the query can be saved normally.
- AI-generated results support cell-click-to-filter and CSV export.

### Security
- Four-layer defense: prompt hardening, output sanitization (SELECT/WITH only,
  single statement, markdown stripping), existing execution guardrails
  (READ ONLY transaction, access control, timeout, hard deny list), and
  input length capping (2000 chars).
- LLM schema context is filtered per-user permissions -- the LLM only sees
  abstract views the user is authorized to access.
- User natural language is isolated in the `user` message role, never
  interpolated into the system prompt.

### Configuration
Feature is disabled by default (`ai_enabled: False`). Example Ollama config:
```python
PLUGINS_CONFIG = {
    "netbox_sqlquery": {
        "ai_enabled": True,
        "ai_provider": "openai",
        "ai_base_url": "http://localhost:11434/v1",
        "ai_model": "qwen2.5-coder:7b",
    }
}
```
