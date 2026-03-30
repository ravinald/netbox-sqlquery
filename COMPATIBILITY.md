# Compatibility

| Plugin version | NetBox version | Python version        |
|----------------|----------------|-----------------------|
| 0.1.x          | 4.0 - 4.5     | 3.10, 3.11, 3.12, 3.13, 3.14 |

## Notes

- Tested on NetBox 4.0.0 (Python 3.11) and NetBox 4.5.5 (Python 3.12).
- NetBox 4.5 removed `is_staff` from the User model. The plugin handles this gracefully.
- Abstract SQL views (`nb_*`) are generated from the database schema at runtime and adapt to the installed NetBox version. Newer NetBox versions produce more views as new models are added.
- The ObjectPermission integration (when `require_superuser` is `False`) uses NetBox's native permission system, available since NetBox 2.10.
