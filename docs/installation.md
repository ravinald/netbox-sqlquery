# Installation

## Requirements

- NetBox 4.0 or later
- Python 3.10, 3.11, or 3.12

## Install from PyPI

```bash
pip install netbox-sqlquery
```

## Configure NetBox

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

## Run migrations

```bash
python manage.py migrate netbox_sqlquery
```

## Collect static files

```bash
python manage.py collectstatic --no-input
```

## Restart NetBox

Restart the NetBox services so the plugin is loaded.

For Docker-based deployments, see [docker.md](docker.md).
