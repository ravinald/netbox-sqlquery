#!/usr/bin/env bash
# ollama-userdata.sh -- EC2 userdata / cloud-init script for an Ollama LLM host
#
# Intended for a c6i.2xlarge (8 vCPU, 16 GB RAM) running Amazon Linux 2023
# or Ubuntu 22.04+. Paste this into the userdata field when launching the
# instance, or pass it via --user-data in the AWS CLI.
#
# What it does:
#   1. Installs Ollama
#   2. Configures it as a systemd service listening on 0.0.0.0:11434
#   3. Tunes parallelism for the available hardware
#   4. Pulls the default model set for SQL generation
#
# Configurable variables (set these before the script runs, or edit below):

OLLAMA_MODELS="${OLLAMA_MODELS:-qwen2.5-coder:7b,llama3.1:8b,codellama:7b}"
OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-2}"
OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}"

set -euo pipefail
exec > >(tee /var/log/ollama-setup.log) 2>&1

echo "=== Ollama host bootstrap started at $(date -u) ==="

# --- Install Ollama ---

echo "Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

# --- Configure systemd service ---

echo "Configuring Ollama service..."
mkdir -p /etc/systemd/system/ollama.service.d

cat > /etc/systemd/system/ollama.service.d/override.conf <<EOF
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_NUM_PARALLEL=${OLLAMA_NUM_PARALLEL}"
Environment="OLLAMA_MAX_LOADED_MODELS=${OLLAMA_MAX_LOADED_MODELS}"
EOF

systemctl daemon-reload
systemctl enable ollama
systemctl start ollama

# --- Wait for service readiness ---

echo "Waiting for Ollama to be ready..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "Ollama is ready."
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "WARNING: Ollama not ready after 60s. Check: systemctl status ollama"
        exit 1
    fi
    sleep 1
done

# --- Pull models ---

echo "Pulling models..."
IFS=',' read -ra MODEL_LIST <<< "$OLLAMA_MODELS"

for model in "${MODEL_LIST[@]}"; do
    model="$(echo "$model" | xargs)"
    echo "Pulling: $model"
    ollama pull "$model" || echo "WARNING: Failed to pull $model"
done

# --- Done ---

echo "=== Ollama host bootstrap complete at $(date -u) ==="
echo "Models available:"
ollama list
echo ""
echo "Listening on 0.0.0.0:11434"
