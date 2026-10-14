# Compatibility

| Plugin version | NetBox version | Python version    |
|----------------|----------------|-------------------|
| 0.3.x          | 4.7.x          | 3.12, 3.13, 3.14 |
| 0.2.x          | 4.6.x          | 3.12, 3.13, 3.14 |
| 0.1.x          | 4.5.x          | 3.12, 3.13, 3.14 |

Each line is pinned to one NetBox minor via `min_version`/`max_version`: install 0.3.x on
NetBox 4.7, 0.2.x on NetBox 4.6, 0.1.x on NetBox 4.5.

## Notes

- Tested on NetBox 4.7.3 (Python 3.12); the 0.2.x line is tested on NetBox 4.6.4 and the 0.1.x line on NetBox 4.5.10.
- NetBox 4.7 runs on Django 6.1, 4.6 on Django 6.0.
- NetBox 4.7 replaced django-mptt with a PostgreSQL `ltree` column. The `nb_*` views omit the tree bookkeeping columns (`path`, `sort_path`, and the older `lft`/`rght`/`tree_id`/`level`); query hierarchy through `parent`, or against the raw table where `path` remains.
- NetBox 4.5 removed `is_staff` from the User model. The plugin is designed for this change.
- Abstract SQL views (`nb_*`) are generated from the database schema at runtime and adapt to the installed NetBox version.
- The ObjectPermission integration uses NetBox's native permission system.
- Earlier NetBox versions (4.0-4.4) are untested and may have migration compatibility issues.

## netbox-branching

The plugin is branch-unaware. Its `nb_*` views are bound to the `main` (`public`) schema, so
the SQL console and NL agent always query `main` data regardless of the active
[netbox-branching](https://netboxlabs.com/docs/extensions/branching/) branch. Plugin
configuration (saved queries, permissions) is global and correct across branches.
