# Installation

## Requirements

- NetBox 4.0 or later
- Python 3.10 or later

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
