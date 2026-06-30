# Installation

## Requirements

- NetBox 4.5 or later
- Python 3.12 or later

## Standalone install

### 1. Install the package

Install into NetBox's virtual environment (adjust the path to match your NetBox installation):

```bash
cd /path/to/netbox
venv/bin/pip install netbox-sqlquery
```

Or install from source:

```bash
cd /path/to/netbox
venv/bin/pip install -e /path/to/netbox-sqlquery
```

### 2. Configure NetBox

Add the plugin to your `configuration.py`:

```python
PLUGINS = ["netbox_sqlquery"]

PLUGINS_CONFIG = {
    "netbox_sqlquery": {
        "require_superuser": True,
        "max_rows": 1000,
        "statement_timeout_ms": 10000,
        "deny_tables": [
            "auth_user",
            "users_token",
            "users_userconfig",
        ],
    }
}
```

See [configuration.md](configuration.md) for all available settings.

### 3. Run migrations

```bash
cd /path/to/netbox
venv/bin/python netbox/manage.py migrate netbox_sqlquery
```

### 4. Collect static files

```bash
venv/bin/python netbox/manage.py collectstatic --no-input
```

### 5. Restart NetBox

Restart all NetBox services (web server and worker) so the plugin is loaded.

## Testing an unreleased version (from source)

When there is no published PyPI package yet — testing a branch before cutting a release —
install directly from a clone. An editable install reads `pyproject.toml`, so dependencies
(including `sqlglot`, used by the SQL safety guards) are pulled in automatically.

### Option A: editable install (fastest iteration)

```bash
# Get the source and the branch under test
git clone https://github.com/ravinald/netbox-sqlquery.git
cd netbox-sqlquery
git checkout feature/llm

# Install into NetBox's venv (resolves sqlglot and other deps)
/opt/netbox/venv/bin/pip install -e .

# Apply migrations and static files, then restart services
/opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py migrate netbox_sqlquery
/opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py collectstatic --no-input
```

Restart all NetBox services (web server **and** worker) afterwards.

Editing the source then restarting NetBox picks up the changes — no reinstall needed.

### Option B: build and install a local wheel (mirrors a real release)

Use this to validate the packaged artifact itself before publishing:

```bash
cd netbox-sqlquery
python -m build                      # requires: pip install build
                                     # writes dist/netbox_sqlquery-<version>-py3-none-any.whl
/opt/netbox/venv/bin/pip install dist/netbox_sqlquery-*.whl
/opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py migrate netbox_sqlquery
/opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py collectstatic --no-input
```

Notes:

- Install with `pip install -e .` (or the wheel), **not** `--no-deps`. Skipping
  dependencies leaves `sqlglot` out; the plugin still runs but falls back to weaker regex
  SQL guards, so you would not be testing the real validation path.
- For a Docker-based source test, see the "Installing from source (development)" section
  of [docker.md](docker.md).

## Upgrading

### Standalone (automatic with NetBox upgrades)

Add the plugin to `local_requirements.txt` in your NetBox root directory:

```
netbox-sqlquery
```

NetBox's `upgrade.sh` script will automatically install/upgrade the plugin, run migrations, and collect static files whenever you upgrade NetBox. The abstract SQL views are recreated on startup.

### Standalone (manual)

```bash
cd /path/to/netbox
venv/bin/pip install --upgrade netbox-sqlquery
venv/bin/python netbox/manage.py migrate netbox_sqlquery
venv/bin/python netbox/manage.py collectstatic --no-input
```

Then restart NetBox services.

### Docker

Rebuild the image and restart the stack:

```bash
docker compose build --no-cache
docker compose down
docker compose up -d
```

Migrations run automatically on container startup.

## Docker install

For netbox-docker deployments, see [docker.md](docker.md).
