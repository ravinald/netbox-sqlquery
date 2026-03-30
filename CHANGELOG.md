# Changelog

## 0.1.1

- Fixed ruff formatting across all Python files
- Fixed test suite to use NetBox's custom User and Group models
- Fixed TablePermission.groups M2M to reference users.Group instead of auth.Group
- Updated CI workflow with correct NetBox version matrix and configuration

## 0.1.0

Initial release.

### SQL Console
- SQL query editor with real-time syntax highlighting and auto-uppercase keywords
- SQL keyword toolbar for quick insertion
- Schema sidebar with search filter and Raw SQL / Views toggle
- Abstract views (`nb_*`) that resolve foreign keys to names and aggregate tags
- Column toggle: click result headers to refine the SELECT clause
- Cell click: click a result value to add a WHERE filter
- CSV export of query results
- Write query support (INSERT, UPDATE, DELETE) for authorized users with confirmation dialog

### Saved queries
- Save and load queries from the editor via modal dialogs
- Private and public visibility levels
- Name validation to prevent injection
- REST API for saved query CRUD
- Saved queries list page

### Permissions
- `require_superuser` quick lockdown mode (default)
- ObjectPermission integration: Can view (read access), Can change (write access)
- Menu-group-based table access tied to NetBox view permissions
- Shared tables for cross-app foreign key targets
- Hard deny list for sensitive tables
- Menu items hidden for users without access

### User preferences
- Syntax highlighting on/off toggle
- Customizable colors for keywords, functions, strings, numbers, operators, and comments
- Skip write confirmation option

### Configuration
- `require_superuser`: restrict to superusers only
- `max_rows`: limit result set size
- `statement_timeout_ms`: PostgreSQL query timeout
- `deny_tables`: hard deny list
- `top_level_menu`: top-level nav or under Plugins dropdown

### Operations
- `manage.py sqlquery_create_views` command to create, preview, or drop abstract views
- Query audit logging
- Statement timeout and max row limits
- Docker support for netbox-docker
