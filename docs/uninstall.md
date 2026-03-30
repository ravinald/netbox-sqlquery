# Uninstalling

Follow these steps to cleanly remove the plugin.

## 1. Drop abstract views

The plugin creates `nb_*` views in the PostgreSQL database. Remove them before uninstalling:

```bash
# Native install
cd /opt/netbox/netbox
python manage.py sqlquery_create_views --drop

# Docker
docker compose exec netbox /opt/netbox/venv/bin/python \
  /opt/netbox/netbox/manage.py sqlquery_create_views --drop
```

## 2. Reverse migrations

Remove the plugin's database tables (SavedQuery, TablePermission, QueryPermission):

```bash
python manage.py migrate netbox_sqlquery zero
```

This drops all tables and permissions created by the plugin's migrations.

## 3. Remove plugin configuration

Edit your NetBox `configuration.py` (or `plugins.py` for Docker deployments):

- Remove `"netbox_sqlquery"` from the `PLUGINS` list
- Remove the `"netbox_sqlquery"` entry from `PLUGINS_CONFIG`

## 4. Uninstall the package

```bash
pip uninstall netbox-sqlquery
```

For Docker deployments, remove the plugin from `plugin_requirements.txt` and rebuild the image.

## 5. Clean up static files

```bash
python manage.py collectstatic --no-input
```

This removes the plugin's static files from the collected static directory.

## 6. Clean up user preferences

The plugin stores per-user preferences under the `plugins.netbox_sqlquery.*` keys in each user's config. These are harmless JSON entries that NetBox ignores once the plugin is removed, but you can clear them with:

```bash
python manage.py shell -c "
from users.models import UserConfig
for config in UserConfig.objects.all():
    changed = False
    for key in list(config.data.get('plugins', {}).get('netbox_sqlquery', {}).keys()):
        config.clear('plugins.netbox_sqlquery.' + key)
        changed = True
    if changed:
        config.save()
print('Done')
"
```

## 7. Restart NetBox

Restart all NetBox services so the plugin is fully unloaded.

## 8. Remove ObjectPermissions (optional)

If you created ObjectPermission records for `SQL query permission`, delete them from Admin > Permissions. They reference a content type that no longer exists and will cause no harm but are unnecessary clutter.
