# Docker

netbox-sqlquery includes ready-to-use files for [netbox-docker](https://github.com/netbox-community/netbox-docker) deployments. These files are in the `docker/` directory of the plugin repo.

## Files

| File                          | Purpose                                                     |
|-------------------------------|-------------------------------------------------------------|
| `Dockerfile-Plugins`          | Builds a custom NetBox image with the plugin installed      |
| `plugin_requirements.txt`     | Lists the pip package to install                            |
| `docker-compose.override.yml` | Overrides all three NetBox services to use the custom image |

## Setup

### 1. Clone netbox-docker

```bash
git clone https://github.com/netbox-community/netbox-docker.git
cd netbox-docker
```

### 2. Copy the plugin docker files

```bash
cp /path/to/netbox-sqlquery/docker/plugin_requirements.txt .
cp /path/to/netbox-sqlquery/docker/Dockerfile-Plugins .
cp /path/to/netbox-sqlquery/docker/docker-compose.override.yml .
```

### 3. Configure the plugin

Edit `configuration/plugins.py` to enable the plugin:

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

### 4. Build and start

```bash
docker compose build --no-cache
docker compose up -d
```

Migrations run automatically on startup. The abstract SQL views are created when the plugin loads.

## How it works

The `Dockerfile-Plugins` extends the official NetBox image by:

1. Installing the plugin via pip from PyPI
2. Copying `configuration/plugins.py` into the image so `collectstatic` can find the plugin's static files
3. Running `collectstatic` to include the editor JavaScript and icon

The `docker-compose.override.yml` ensures all three NetBox services use the custom image:

- `netbox` (web server)
- `netbox-worker` (background tasks)
- `netbox-housekeeping` (scheduled maintenance)

Omitting any of these services is a common mistake that leaves containers running without the plugin.

## Installing from source (development)

To install from a local clone instead of PyPI, replace `plugin_requirements.txt` with a direct install in the Dockerfile:

```dockerfile
FROM netboxcommunity/netbox:latest

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/
COPY ./netbox-sqlquery /opt/netbox-sqlquery
RUN /usr/local/bin/uv pip install -e /opt/netbox-sqlquery

COPY ./configuration/plugins.py /etc/netbox/config/plugins.py
RUN DEBUG="true" \
    SECRET_KEY="collectstatic-build-key-not-for-production-use-0123456789" \
    /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py collectstatic --no-input
```

Then copy the plugin source into your netbox-docker directory:

```bash
cp -r /path/to/netbox-sqlquery ./netbox-sqlquery
```

## Running migrations manually

Migrations run automatically on startup. To run them manually:

```bash
docker compose exec netbox \
  /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py migrate netbox_sqlquery
```

## Recreating abstract views

If views need to be rebuilt (e.g., after a NetBox upgrade):

```bash
docker compose exec netbox \
  /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py sqlquery_create_views
```
