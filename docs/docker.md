# Docker

netbox-sqlquery includes ready-to-use files for [netbox-docker](https://github.com/netbox-community/netbox-docker) deployments.

## Setup

1. Clone netbox-docker:

```bash
git clone https://github.com/netbox-community/netbox-docker.git
cd netbox-docker
```

2. Copy the files from the `docker/` directory in this repo:

```bash
cp /path/to/netbox-sqlquery/docker/plugin_requirements.txt .
cp /path/to/netbox-sqlquery/docker/Dockerfile-Plugins .
cp /path/to/netbox-sqlquery/docker/docker-compose.override.yml .
```

3. Add the plugin to your NetBox configuration. Create or edit `configuration/plugins.py`:

```python
PLUGINS = ["netbox_sqlquery"]
```

4. Build and start:

```bash
docker compose build --no-cache
docker compose up -d
```

## How it works

The `Dockerfile-Plugins` builds a custom image based on the official NetBox image. It installs the plugin via pip and runs `collectstatic` to include the editor assets.

The `docker-compose.override.yml` ensures all three NetBox services (`netbox`, `netbox-worker`, `netbox-housekeeping`) use the custom image. Omitting any of these services is a common mistake that leaves containers running without the plugin.

## Running migrations manually

Migrations run automatically on startup. To run them manually:

```bash
docker compose exec netbox \
  /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py migrate netbox_sqlquery
```
