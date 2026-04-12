# Bootstrapping an Ollama LLM Host

This covers standing up a dedicated Ollama instance for the netbox-sqlquery plugin's natural language query feature. The host serves as a shared inference endpoint that any number of NetBox instances can point at.

The workload is lightweight: short prompts in, short SQL out, low concurrency. No GPU needed.

## Instance Specification

| Setting | Value |
|---------|-------|
| Instance type | **c6i.2xlarge** |
| vCPU | 8 |
| RAM | 16 GB |
| Root EBS | 40 GB gp3 |
| AMI | Amazon Linux 2023 or Ubuntu 22.04+ |

Why c6i over m6i: LLM inference on CPU is compute-bound (matrix multiplication). The higher per-core clock of compute-optimized instances translates directly to faster token generation. The 16 GB on a c6i.2xlarge is enough for one loaded 7B model (~4-5 GB) with plenty of OS headroom.

If you need two models loaded simultaneously for A/B testing without swap delays, step up to a **c6i.4xlarge** (16 vCPU, 32 GB).

## Security Group Rules

The Ollama API listens on port **11434** and has no built-in authentication. Lock it down at the network level.

### Inbound

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 11434 | TCP | NetBox instance SG(s) | Ollama API |
| 22 | TCP | Your bastion / VPN CIDR | SSH admin access |

### Outbound

| Port | Protocol | Destination | Purpose |
|------|----------|-------------|---------|
| 443 | TCP | 0.0.0.0/0 | Ollama model downloads (initial setup only) |

Do **not** expose port 11434 to the internet or to broad internal CIDRs. The API accepts arbitrary prompts and returns arbitrary text with no auth layer. Scope the inbound rule to the specific security group(s) attached to your NetBox hosts.

If your environment requires tighter egress controls, the outbound 443 rule is only needed during initial model pulls. After setup you can restrict it to your internal package mirrors if desired.

## Launching the Instance

### Option A: AWS CLI

```bash
aws ec2 run-instances \
  --image-id ami-0abcdef1234567890 \
  --instance-type c6i.2xlarge \
  --key-name your-keypair \
  --security-group-ids sg-xxxxxxxxxxxxxxxxx \
  --subnet-id subnet-xxxxxxxxxxxxxxxxx \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":40,"VolumeType":"gp3"}}]' \
  --user-data file://scripts/ollama-userdata.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ollama-llm},{Key=Service,Value=netbox-sqlquery}]'
```

### Option B: Console

1. Launch a c6i.2xlarge with your preferred AMI
2. Attach the security group with the rules above
3. Under **Advanced Details > User data**, paste the contents of `scripts/ollama-userdata.sh`
4. Set root volume to 40 GB gp3

### Option C: Existing automation

Pass `scripts/ollama-userdata.sh` as the userdata in whatever launch mechanism your team uses (Terraform `user_data`, CloudFormation `UserData`, ASG launch template, etc.).

## What the Userdata Script Does

The script at `scripts/ollama-userdata.sh` runs on first boot and handles everything:

1. Installs Ollama via the official installer
2. Creates a systemd override that binds to `0.0.0.0:11434` and sets performance tuning
3. Enables and starts the service
4. Pulls three models for A/B comparison:
   - `qwen2.5-coder:7b` -- code-specialized, tends to produce the cleanest SQL
   - `llama3.1:8b` -- general-purpose baseline
   - `codellama:7b` -- another code-focused option

All output is logged to `/var/log/ollama-setup.log`. Model pulls take a few minutes depending on network speed. The instance is ready to serve once the script completes.

### Customizing models

Set the `OLLAMA_MODELS` variable before the script runs to change what gets pulled:

```bash
# In your userdata wrapper or launch template:
export OLLAMA_MODELS="qwen2.5-coder:7b"
```

Or edit the variable at the top of the script directly.

## Connecting NetBox

On each NetBox instance, add to `configuration.py`:

```python
PLUGINS_CONFIG = {
    "netbox_sqlquery": {
        "ai_enabled": True,
        "ai_provider": "openai",
        "ai_base_url": "http://<ollama-host-ip-or-dns>:11434/v1",
        "ai_model": "qwen2.5-coder:7b",
    }
}
```

Restart NetBox after changing the config. The plugin makes standard HTTP calls to the Ollama host; there's no agent or sidecar to install on the NetBox side.

To switch models for A/B testing, change `ai_model` and restart. All three models are already pulled on the host.

## Verifying the Setup

From a NetBox host (or anywhere with network access to the Ollama host):

```bash
# Check Ollama is responding
curl -s http://<ollama-host>:11434/api/tags | python3 -m json.tool

# Test a quick generation
curl -s http://<ollama-host>:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder:7b",
    "messages": [{"role": "user", "content": "SELECT 1"}],
    "temperature": 0
  }' | python3 -m json.tool
```

From the Ollama host itself:

```bash
# Check service status
systemctl status ollama

# View setup log
cat /var/log/ollama-setup.log

# List loaded models
ollama list

# Check resource usage
ollama ps
```

## Performance Tuning

The userdata script sets two key parameters via the systemd override at `/etc/systemd/system/ollama.service.d/override.conf`:

| Variable | Default | What it controls |
|----------|---------|------------------|
| `OLLAMA_NUM_PARALLEL` | 2 | Concurrent requests per loaded model |
| `OLLAMA_MAX_LOADED_MODELS` | 1 | Models kept in memory at once |

On a c6i.2xlarge with 16 GB, keeping one model loaded and allowing 2 parallel requests is the right balance. If you find queries queuing up (unlikely at typical NetBox usage levels), you can bump `OLLAMA_NUM_PARALLEL` to 4 at the cost of slightly slower individual responses.

To change these after initial setup:

```bash
sudo systemctl edit ollama
# Edit the Environment lines
sudo systemctl restart ollama
```

## Cost

A c6i.2xlarge runs about $0.34/hr on-demand in us-east-1. For a persistent shared service, a 1-year reserved instance or compute savings plan drops that to roughly $0.20/hr (~40% savings).

If the LLM host doesn't need to be available 24/7 (e.g., dev/staging only), stopping it outside business hours is an easy win.
