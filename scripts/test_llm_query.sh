#!/usr/bin/env bash
# test_llm_query.sh - Test LLM query generation outside of NetBox
#
# Usage:
#   ./scripts/test_llm_query.sh "show me all virtual machines"
#   ./scripts/test_llm_query.sh "list private IPs in usw2" http://localhost:11434
#   ./scripts/test_llm_query.sh "list VMs" http://localhost:11434 llama3.1:8b
#
# Uses the same schema and system prompt as the plugin so results match
# what you'd get in the NetBox UI.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCHEMA_FILE="${SCRIPT_DIR}/netbox_schema.txt"

QUERY="${1:?Usage: $0 \"natural language query\" [ollama_url] [model]}"
OLLAMA_URL="${2:-http://localhost:11434}"
MODEL="${3:-qwen2.5-coder:7b}"

if [ ! -f "$SCHEMA_FILE" ]; then
    echo "ERROR: Schema file not found at $SCHEMA_FILE"
    echo "Generate it from a NetBox instance with:"
    echo "  manage.py shell -c 'from netbox_sqlquery.llm import build_schema_text; from users.models import User; u=User.objects.filter(is_superuser=True).first(); print(build_schema_text(u))' > scripts/netbox_schema.txt"
    exit 1
fi

SCHEMA=$(cat "$SCHEMA_FILE")

SYSTEM_PROMPT="You are a SQL query generator for a PostgreSQL database containing network infrastructure data (NetBox).

Given a natural language question, generate a single SELECT query using ONLY the tables and columns listed below.

Rules:
- Use ONLY SELECT statements. Never generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, or any other non-SELECT statement.
- Use ONLY the tables and columns listed below. Do not reference any other tables or columns.
- Return ONLY the raw SQL query. No explanations, no markdown fencing, no comments, no preamble.
- Generate exactly one SQL statement. Do not include a trailing semicolon.
- For JSON fields (jsonb type), use PostgreSQL JSON operators: ->> for text extraction, -> for nested access, ? for key existence, jsonb_each_text() for iteration.
- When filtering, use ILIKE for case-insensitive text matching where appropriate.
- Use table aliases to keep the query readable when joining multiple tables.

Available tables and columns:

${SCHEMA}"

# Build JSON payload using python to handle escaping properly
PAYLOAD=$(python3 -c "
import json, sys
print(json.dumps({
    'model': sys.argv[1],
    'messages': [
        {'role': 'system', 'content': sys.argv[2]},
        {'role': 'user', 'content': sys.argv[3]},
    ],
    'stream': False,
    'options': {
        'temperature': 0,
        'num_ctx': 8192,
    },
}))
" "$MODEL" "$SYSTEM_PROMPT" "$QUERY")

echo "=== Request ==="
echo "URL:   $OLLAMA_URL/api/chat"
echo "Model: $MODEL"
echo "Query: $QUERY"
echo "Schema: $(echo "$SCHEMA" | grep -c 'Table:') tables, $(echo "$SCHEMA" | wc -c | tr -d ' ') chars"
echo ""

START=$(date +%s)

RESPONSE=$(curl -s --max-time 120 "$OLLAMA_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")
CURL_EXIT=$?

END=$(date +%s)
ELAPSED=$((END - START))

if [ $CURL_EXIT -ne 0 ]; then
    echo "ERROR: curl failed with exit code $CURL_EXIT (timeout or connection error)"
    exit 1
fi

echo "=== Generated SQL ==="
SQL=$(python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d.get('message', {}).get('content', 'NO CONTENT'))
" <<< "$RESPONSE" 2>/dev/null) || SQL="Failed to parse response"
echo "$SQL"

echo ""
echo "=== Timing ==="
python3 -c "
import json, sys
d = json.load(sys.stdin)
total = d.get('total_duration', 0) / 1e9
load = d.get('load_duration', 0) / 1e9
prompt = d.get('prompt_eval_duration', 0) / 1e9
gen = d.get('eval_duration', 0) / 1e9
prompt_tok = d.get('prompt_eval_count', 0)
gen_tok = d.get('eval_count', 0)
print(f'Total:   {total:.1f}s')
print(f'Load:    {load:.1f}s')
print(f'Prompt:  {prompt:.1f}s ({prompt_tok} tokens)')
print(f'Generate: {gen:.1f}s ({gen_tok} tokens, {gen_tok/gen:.1f} tok/s)' if gen > 0 else f'Generate: {gen:.1f}s ({gen_tok} tokens)')
" <<< "$RESPONSE" 2>/dev/null || echo "Wall time: ${ELAPSED}s"
