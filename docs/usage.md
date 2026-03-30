# Usage

## Accessing the query view

Navigate to SQL Query > SQL Console in the NetBox menu (or Plugins > SQL Query if `top_level_menu` is disabled). Access is controlled by the `require_superuser` setting and ObjectPermissions. See [permissions.md](permissions.md).

## Writing queries

The editor accepts `SELECT` and `WITH...SELECT` queries for all users. Superusers (or users with the `change` permission) can also run `INSERT`, `UPDATE`, and `DELETE` queries.

### Raw SQL vs Views mode

Toggle between **Raw SQL** and **Views** using the buttons above the schema sidebar.

**Views mode** uses abstract views (`nb_*`) that resolve foreign keys to human-readable names and aggregate tags. This matches how data appears in the NetBox UI:

<img src="images/view-query.png" alt="Views mode query" width="700">

**Raw SQL mode** queries the actual database tables directly, giving full control for complex queries:

<img src="images/raw-query.png" alt="Raw SQL query" width="700">

### SQL keyword toolbar

The toolbar above the editor provides buttons for common SQL keywords. Clicking a button inserts the keyword at the cursor position.

### Schema sidebar

The sidebar on the left lists all tables you have permission to access. Use the **search field** to filter tables by name or column name. Each table expands to show its columns and data types. Click a table or column name to insert it into the editor.

### Syntax highlighting

The editor provides real-time SQL syntax highlighting with color-coded keywords, functions, strings, numbers, operators, and comments. SQL keywords are auto-capitalized as you type.

Toggle highlighting on/off with the highlight button next to Run query. Customize colors in User Preferences under the SQL Query section.

<img src="images/user-preferences.png" alt="User preferences" width="700">

### Keyboard shortcuts

- **Ctrl+Enter** (or Cmd+Enter on macOS): execute the query
- **Tab**: inserts two spaces

## Running queries

Click **Run query** or press Ctrl+Enter. Results appear below the editor as a scrollable table.

### Column toggle

Click a column header in the results to deselect it. The SQL is rewritten to exclude that column. Click again to re-enable. Run the query to execute the refined SQL.

<img src="images/view-query-column-select.png" alt="Column selection" width="700">

### Cell filtering

Click a cell value in the results to add a WHERE filter for that column and value. The filter is appended to the SQL. Run the query to apply.

### CSV export

Click the **Download CSV** button below the results to export the current result set.

## Saving and loading queries

Click **Save** (floppy disk icon) to save the current query with a name and visibility level.

<img src="images/saving-query.png" alt="Save query dialog" width="350">

Click **Load** (folder icon) to browse and search saved queries. See [saved-queries.md](saved-queries.md).

## Write queries

INSERT, UPDATE, and DELETE queries are available to superusers and users with the `change` permission on SQL query permission. A confirmation dialog is shown before execution. Write query results show the number of affected rows and the modified data.

## Query limits

- Results are capped at the configured `max_rows` value (default: 1000)
- Queries are cancelled if they exceed `statement_timeout_ms` (default: 10 seconds)
- Read queries run inside a read-only transaction as a database-level safety guard
