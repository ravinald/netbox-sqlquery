# Local development stack

A self-contained NetBox + Postgres + Redis stack for testing unreleased plugin code —
separate from any dev/prod NetBox you run elsewhere. The plugin is installed editable and
the working tree is bind-mounted, so template and Python edits show on a browser refresh.

## Requirements

- Docker Engine + Compose v2, on any Linux host (a VM works well), macOS Docker Desktop,
  Colima, or OrbStack.
- The stack pins `netboxcommunity/netbox:v4.5.10` by default. Override with `NETBOX_IMAGE`
  (e.g. `v4.6.4`) to test another NetBox line.

## Start

```bash
cd dev
docker compose up -d --build      # first run builds the plugin image
docker compose logs -f netbox     # watch migrations + startup
```

Browse to `http://<docker-host>:8000/` and log in as `admin` / `admin`. The editor lives at
`http://<docker-host>:8000/plugins/sqlquery/`.

If you reach it from a different host than where Docker runs (e.g. a VM), add that origin to
`CSRF_TRUSTED_ORIGINS` in `dev/netbox.env` or POSTs (login, query runs) will be rejected.

## Iterate

- **Templates / Python** (e.g. inline CSS in `query.html`, `access.py`): edit, refresh the
  browser. `DEBUG=true` disables template caching, and the editable install resolves to the
  bind-mounted source.
- **Static JS/CSS** (`static/netbox_sqlquery/editor.js`): re-collect, then hard-refresh:
  ```bash
  docker compose exec netbox /opt/netbox/venv/bin/python \
    /opt/netbox/netbox/manage.py collectstatic --no-input
  ```
- **Editing from another machine:** if the source lives on your workstation and Docker runs
  on a VM, `rsync` the tree over after each change:
  ```bash
  rsync -az --delete --exclude .git --exclude __pycache__ \
    ./ ravi@<vm>:~/netbox-sqlquery/
  ```

## Run the test suite

```bash
docker compose exec netbox /opt/netbox/venv/bin/python \
  /opt/netbox/netbox/manage.py test netbox_sqlquery
```

## Switch NetBox version

```bash
NETBOX_IMAGE=netboxcommunity/netbox:v4.6.4 docker compose up -d --build
```

## Tear down

```bash
docker compose down          # keep the database volume
docker compose down -v       # also wipe Postgres data
```
