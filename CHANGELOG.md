# Changelog

## 0.2.0

- NetBox 4.6 support (Django 6.0); `min_version` is now 4.6.0. For NetBox 4.5.x, use the 0.1.x line.
- Query access for the new 4.6 tables: cable bundles, rack groups, and virtual machine types.
- Documented branch-unaware behavior with netbox-branching: the SQL console and NL agent always query the `main` schema.

## 0.1.8

- Natural-language-to-SQL agent: a tool-calling loop (list/describe/lookup/dry-run/submit) over the query engine that enforces per-user permissions on every step, replacing the earlier one-shot generation.
- SQL safety guards backed by sqlglot: single read-only SELECT/WITH proof and hallucinated-column detection.
- Few-shot store (`NLExample`) that learns from accepted queries.
- Fixed syntax-highlight caret drift in the editor (#6).
- Pinned to NetBox 4.5.x (`max_version`); NetBox 4.6 requires plugin 0.2.x.

Releases 0.1.3–0.1.7 shipped incremental fixes; see the GitHub Releases for details.

## 0.1.2

- Fixed package to include templates and static files in the wheel (broken in 0.1.0 and 0.1.1)

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
