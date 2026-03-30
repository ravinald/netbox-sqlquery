# Operations

## Management commands

### `sqlquery_create_views`

Creates or replaces the abstract SQL views (`nb_*`) that the Views mode uses. These views are normally created automatically when NetBox starts, but the command is useful for troubleshooting, rebuilding after a NetBox upgrade, or inspecting the generated SQL.

**Recreate all views:**

```bash
# Native install
cd /opt/netbox/netbox
python manage.py sqlquery_create_views

# Docker
docker compose exec netbox /opt/netbox/venv/bin/python \
  /opt/netbox/netbox/manage.py sqlquery_create_views
```

**Preview the SQL without executing:**

```bash
python manage.py sqlquery_create_views --dry-run
```

This prints the `CREATE OR REPLACE VIEW` statements for all 87+ views without running them. Useful for reviewing what the plugin generates or debugging view creation failures.

**Drop all abstract views:**

```bash
python manage.py sqlquery_create_views --drop
```

Removes all `nb_*` views from the database. The Views mode in the sidebar will show an empty list until views are recreated.

### When to run

- **After a NetBox upgrade**: If NetBox adds, removes, or renames database columns, the abstract views may reference stale columns. Re-running the command rebuilds them from the current schema.
- **After plugin installation**: Views are created automatically on first startup. If that fails (e.g., database permissions), run the command manually.
- **After restoring a database backup**: If the backup doesn't include views, recreate them.
- **For debugging**: Use `--dry-run` to inspect the SQL that would be generated for each model.

## REST API endpoints

The plugin provides REST API endpoints for saved query management:

```
GET    /api/plugins/sqlquery/saved-queries/        List saved queries
POST   /api/plugins/sqlquery/saved-queries/        Create a saved query
GET    /api/plugins/sqlquery/saved-queries/{id}/    Retrieve a saved query
PUT    /api/plugins/sqlquery/saved-queries/{id}/    Update a saved query
DELETE /api/plugins/sqlquery/saved-queries/{id}/    Delete a saved query
```

Authentication is required. The list endpoint returns only queries visible to the requesting user (owned queries plus public queries).

## Internal AJAX endpoints

These endpoints are used by the query editor UI and are not intended for external use:

```
POST   /plugins/sqlquery/ajax/save-query/          Save a query from the editor
GET    /plugins/sqlquery/ajax/list-queries/         List queries for the load dialog
GET    /plugins/sqlquery/ajax/list-queries/?q=term  Search queries by name
```

## Logging

All executed queries are logged with the username and truncated SQL (first 500 characters) at the INFO level under the `netbox_sqlquery` logger. Configure logging in your NetBox `configuration.py` or `logging.py`:

```python
LOGGING = {
    "loggers": {
        "netbox_sqlquery": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}
```

Log entries look like:

```
INFO query user=admin sql=SELECT * FROM nb_prefixes WHERE status = 'active'
```

## Caching

The plugin caches two things:

- **Raw schema** (`netbox_sqlquery_schema`): Table and column metadata from `information_schema`. TTL: 300 seconds.
- **Abstract schema** (`netbox_sqlquery_abstract_schema`): Column metadata for `nb_*` views. TTL: 300 seconds.

To force a schema refresh, clear the Django cache or restart NetBox. The cache is per-process using Django's default cache backend.

## Troubleshooting

### Views mode shows no tables

The abstract views may not have been created. Run:

```bash
python manage.py sqlquery_create_views
```

If this fails, check that the database user has `CREATE` privilege on the `public` schema.

### "Access denied to: users_owner" or similar

A query references a table not in the user's allowed set. Common causes:

- The table is a cross-app FK target not in the shared tables list. This is a bug – report it.
- The user lacks the NetBox view permission for the relevant menu group. Grant the appropriate permission (e.g., `ipam.view_ipaddress` for IPAM tables).

### Saved queries page returns 500

Check the NetBox error log. Common causes:

- Missing database migration: run `python manage.py migrate netbox_sqlquery`
- Plugin version mismatch after upgrade: rebuild and restart

### Syntax highlighting not visible

- Hard-refresh the browser (Ctrl+Shift+R) to clear cached JS
- Check User Preferences > SQL Query: Syntax highlighting is set to "On"
- Check `localStorage` in the browser console: `localStorage.getItem("sqlquery_highlight")` should be `"on"` or `null`

### Abstract views return stale data after NetBox upgrade

Re-run `python manage.py sqlquery_create_views` to regenerate views from the current schema.
