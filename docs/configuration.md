# Configuration

All settings go in your `PLUGINS_CONFIG` dictionary in `configuration.py`.

## Settings

### `require_superuser`

- Type: `bool`
- Default: `True`

When `True`, only superusers can access the query view. When `False`, access is controlled by NetBox's ObjectPermission system -- users need the `view_query` permission on the `netbox_sqlquery.querypermission` object type.

### `max_rows`

- Type: `int`
- Default: `1000`

Maximum number of rows returned per query. Results are truncated at this limit.

### `statement_timeout_ms`

- Type: `int`
- Default: `10000`

PostgreSQL statement timeout in milliseconds. Queries that exceed this limit are cancelled by the database.

### `deny_tables`

- Type: `list[str]`
- Default: `["auth_user", "users_token", "users_userconfig"]`

Tables that are blocked for all users, including superusers, when accessed through the plugin. This is a hard deny that cannot be overridden.

### `top_level_menu`

- Type: `bool`
- Default: `False`

When `True`, the plugin gets its own top-level entry in the NetBox navigation bar. When `False`, it appears under the shared "Plugins" dropdown. Requires a NetBox restart to take effect.

## User preferences

Per-user preferences are available under User Preferences in the NetBox UI, grouped under the "Plugins" section with "SQL Query:" prefix labels.

- **Syntax highlighting**: Enable/disable real-time SQL highlighting and auto-uppercase
- **Color settings**: Customize colors for keywords, functions, strings, numbers, operators, and comments using NetBox's color palette
- **Skip write confirmation**: Skip the confirmation dialog for write queries (superuser/execute_write only)

## Example

```python
PLUGINS_CONFIG = {
    "netbox_sqlquery": {
        "require_superuser": False,
        "max_rows": 5000,
        "statement_timeout_ms": 30000,
        "deny_tables": [
            "auth_user",
            "users_token",
            "users_userconfig",
            "secrets_secret",
        ],
        "top_level_menu": True,
    }
}
```
