#!/usr/bin/env bash
#
# setup_ollama.sh - Install Ollama and pull models for netbox-sqlquery AI queries
#
# This sets up a shared Ollama instance that multiple NetBox instances can
# connect to. No GPU required -- the SQL generation workload (short input,
# short output, low concurrency) runs well on CPU-only hardware.
#
# Recommended instance sizing (CPU-only, compute-optimized):
#
#   LLM inference is compute-bound (matrix math), so c6i (compute-optimized)
#   gives better per-core performance than m6i for the same price.
#
#   Recommended  c6i.2xlarge   8 vCPU, 16 GB RAM, 40 GB disk
#   Multi-model  c6i.4xlarge  16 vCPU, 32 GB RAM, 60 GB disk
#
#   A 7B Q4-quantized model uses ~4-5 GB RAM. The c6i.2xlarge leaves
#   comfortable headroom for the OS and Ollama overhead. Response times
#   for a SQL query (~100-300 tokens) are roughly 5-10s on 8 cores,
#   which is fine for an interactive "Thinking..." wait.
#
#   The c6i.4xlarge is only needed if you want two models loaded
#   simultaneously for A/B testing without model swap delays.
#
# Usage:
#   ./scripts/setup_ollama.sh                          # Install + pull all default models
#   ./scripts/setup_ollama.sh --models "llama3.1:8b"   # Install + pull specific models
#   ./scripts/setup_ollama.sh --skip-install            # Only pull models (Ollama already installed)
#
# Default models (for A/B testing SQL generation quality):
#   - qwen2.5-coder:7b    - Code-specialized, strong at SQL generation
#   - llama3.1:8b          - General-purpose, good baseline
#   - codellama:7b         - Meta's code model
#
# After running, configure your NetBox PLUGINS_CONFIG with one of the pulled
# models. Point ai_base_url to this host from every NetBox instance that
# should have AI query support.

set -euo pipefail

DEFAULT_MODELS="qwen2.5-coder:7b,llama3.1:8b,codellama:7b"
MODELS=""
SKIP_INSTALL=false

# Ollama performance tuning for CPU-only, shared-service use.
# OLLAMA_NUM_PARALLEL:      max concurrent requests per model (default 1)
# OLLAMA_MAX_LOADED_MODELS: models kept in memory simultaneously (default 1)
#
# With 16 GB RAM and one 7B model loaded, 2 parallel requests is safe.
# With 32 GB RAM you can keep 2 models loaded and bump parallelism to 4.
OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-2}"
OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --models <list>    Comma-separated list of models to pull (default: ${DEFAULT_MODELS})"
    echo "  --skip-install     Skip Ollama installation, only pull models"
    echo "  -h, --help         Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  OLLAMA_NUM_PARALLEL       Max concurrent requests per model (default: 2)"
    echo "  OLLAMA_MAX_LOADED_MODELS  Models kept in memory at once (default: 1)"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --models)
            MODELS="$2"
            shift 2
            ;;
        --skip-install)
            SKIP_INSTALL=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

MODELS="${MODELS:-$DEFAULT_MODELS}"

# --- System checks ---

echo "==> Checking system resources..."

TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0)
TOTAL_RAM_GB=$(( TOTAL_RAM_KB / 1024 / 1024 ))
CPU_COUNT=$(nproc 2>/dev/null || echo 0)

if [ "$TOTAL_RAM_GB" -gt 0 ]; then
    echo "    RAM:  ${TOTAL_RAM_GB} GB"
    echo "    CPUs: ${CPU_COUNT}"

    if [ "$TOTAL_RAM_GB" -lt 8 ]; then
        echo ""
        echo "    WARNING: Less than 8 GB RAM detected. A 7B model needs ~4-5 GB."
        echo "    The system may swap heavily. 16 GB is recommended."
        echo ""
        read -rp "    Continue anyway? [y/N] " confirm
        if [[ ! "$confirm" =~ ^[yY] ]]; then
            echo "Aborted."
            exit 1
        fi
    fi

    # Auto-tune based on available RAM
    if [ "$TOTAL_RAM_GB" -ge 32 ]; then
        OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-2}"
        OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-4}"
        echo "    Tuning: 32+ GB detected, allowing 2 loaded models and 4 parallel requests."
    fi
else
    echo "    Could not detect system resources (not Linux?). Proceeding with defaults."
fi

# --- Install Ollama ---

if [ "$SKIP_INSTALL" = false ]; then
    echo ""
    echo "==> Installing Ollama..."

    if command -v ollama &>/dev/null; then
        echo "    Ollama is already installed: $(ollama --version)"
        echo "    Skipping installation."
    else
        if [[ "$(uname -s)" != "Linux" ]]; then
            echo "ERROR: This install script targets Linux. For macOS, install via: brew install ollama"
            exit 1
        fi

        curl -fsSL https://ollama.com/install.sh | sh
        echo "    Ollama installed successfully."
    fi

    # Configure systemd service with performance tuning
    if command -v systemctl &>/dev/null; then
        echo "==> Configuring Ollama service..."

        # Create systemd override for environment variables
        OVERRIDE_DIR="/etc/systemd/system/ollama.service.d"
        sudo mkdir -p "$OVERRIDE_DIR"
        sudo tee "$OVERRIDE_DIR/netbox-sqlquery.conf" > /dev/null <<SYSTEMD
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_NUM_PARALLEL=${OLLAMA_NUM_PARALLEL}"
Environment="OLLAMA_MAX_LOADED_MODELS=${OLLAMA_MAX_LOADED_MODELS}"
SYSTEMD
        echo "    Set OLLAMA_HOST=0.0.0.0:11434 (listen on all interfaces)"
        echo "    Set OLLAMA_NUM_PARALLEL=${OLLAMA_NUM_PARALLEL}"
        echo "    Set OLLAMA_MAX_LOADED_MODELS=${OLLAMA_MAX_LOADED_MODELS}"

        sudo systemctl daemon-reload
        sudo systemctl enable ollama 2>/dev/null || true
        sudo systemctl restart ollama 2>/dev/null || true

        # Wait for the service to be ready
        echo "    Waiting for Ollama to be ready..."
        for i in $(seq 1 30); do
            if ollama list &>/dev/null 2>&1; then
                echo "    Ollama is ready."
                break
            fi
            if [ "$i" -eq 30 ]; then
                echo "    WARNING: Ollama did not become ready in 30s. Check: systemctl status ollama"
            fi
            sleep 1
        done
    fi
else
    echo "==> Skipping Ollama installation (--skip-install)."
    if ! command -v ollama &>/dev/null; then
        echo "ERROR: Ollama is not installed. Remove --skip-install to install it."
        exit 1
    fi
fi

# --- Pull models ---

echo ""
echo "==> Pulling models for A/B testing..."

IFS=',' read -ra MODEL_LIST <<< "$MODELS"
PULLED=()
FAILED=()

for model in "${MODEL_LIST[@]}"; do
    model="$(echo "$model" | xargs)"  # trim whitespace
    echo ""
    echo "--- Pulling: $model ---"
    if ollama pull "$model"; then
        PULLED+=("$model")
    else
        echo "    WARNING: Failed to pull $model"
        FAILED+=("$model")
    fi
done

# --- Summary ---

HOSTNAME=$(hostname -f 2>/dev/null || hostname)

echo ""
echo "============================================"
echo "  Ollama Setup Complete"
echo "============================================"
echo ""

if [ ${#PULLED[@]} -gt 0 ]; then
    echo "Models ready:"
    for model in "${PULLED[@]}"; do
        echo "  - $model"
    done
fi

if [ ${#FAILED[@]} -gt 0 ]; then
    echo ""
    echo "Failed to pull:"
    for model in "${FAILED[@]}"; do
        echo "  - $model"
    done
fi

echo ""
echo "Service config:"
echo "  Listening:        0.0.0.0:11434"
echo "  Parallel requests: ${OLLAMA_NUM_PARALLEL}"
echo "  Loaded models:     ${OLLAMA_MAX_LOADED_MODELS}"

echo ""
echo "============================================"
echo "  NetBox Configuration"
echo "============================================"
echo ""
echo "Add one of the following to your NetBox configuration.py"
echo "on each NetBox instance that should have AI query support."
echo ""
echo "Replace the base_url hostname with this server's address"
echo "as reachable from your NetBox instances."
echo ""

for model in "${PULLED[@]}"; do
    cat <<EOF
# --- Using: $model ---
PLUGINS_CONFIG = {
    "netbox_sqlquery": {
        "ai_enabled": True,
        "ai_provider": "openai",
        "ai_base_url": "http://${HOSTNAME}:11434/v1",
        "ai_model": "$model",
    }
}

EOF
done

echo "To switch models for A/B testing, change ai_model and restart NetBox."
echo "List installed models: ollama list"
