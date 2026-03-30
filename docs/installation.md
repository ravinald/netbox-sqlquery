# Installation

## Requirements

- NetBox 4.0 or later
- Python 3.10 or later

## Standalone install

### 1. Install the package

```bash
pip install netbox-sqlquery
```

Or install from source:

```bash
pip install -e /path/to/netbox-sqlquery
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
cd /opt/netbox/netbox
python manage.py migrate netbox_sqlquery
```

### 4. Collect static files

```bash
python manage.py collectstatic --no-input
```

### 5. Restart NetBox

Restart all NetBox services (web server and worker) so the plugin is loaded.

## Docker install

For netbox-docker deployments, see [docker.md](docker.md).
