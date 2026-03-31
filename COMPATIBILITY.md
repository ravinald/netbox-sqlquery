# Compatibility

| Plugin version | NetBox version | Python version    |
|----------------|----------------|-------------------|
| 0.1.x          | 4.5+           | 3.12, 3.13, 3.14 |

## Notes

- Tested on NetBox 4.5.5 (Python 3.12).
- NetBox 4.5 removed `is_staff` from the User model. The plugin is designed for this change.
- Abstract SQL views (`nb_*`) are generated from the database schema at runtime and adapt to the installed NetBox version.
- The ObjectPermission integration uses NetBox's native permission system.
- Earlier NetBox versions (4.0-4.4) are untested and may have migration compatibility issues.
