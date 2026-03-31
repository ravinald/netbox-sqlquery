# Saved queries

Saved queries let users store and reuse SQL queries within the plugin.

## Saving a query

1. Write or run a query in the editor
2. Click the **Save** button (floppy disk icon) next to Run query
3. Enter a name, optional description, and visibility level
4. Click Save

<img src="images/saving-query.png" alt="Save query dialog" width="350">

Query names must start with a letter or number and can contain letters, numbers, spaces, hyphens, underscores, and periods. Special characters are rejected to prevent injection attacks.

## Loading a saved query

1. Click the **Load** button (folder icon) next to Save
2. A dialog shows all queries visible to you, with a search bar
3. Click a query to load it into the editor

## Visibility levels

- **Private**: Only visible to you.
- **Public (read-only)**: Visible to all authenticated users. Only you can edit or delete it.

## Managing saved queries

The full list of saved queries is available at SQL Query > Saved Queries (or `/plugins/sqlquery/saved-queries/`). From there you can view, edit, and delete queries.

<img src="images/saved-query-list.png" alt="Saved queries list" width="700">

Clicking a query name shows its details:

<img src="images/saved-query-view.png" alt="Saved query detail" width="700">

## REST API

The API supports full CRUD operations and query execution:

```
GET    /api/plugins/sqlquery/saved-queries/                List saved queries
POST   /api/plugins/sqlquery/saved-queries/                Create a saved query
GET    /api/plugins/sqlquery/saved-queries/{id}/            Retrieve a saved query
PUT    /api/plugins/sqlquery/saved-queries/{id}/            Update a saved query
DELETE /api/plugins/sqlquery/saved-queries/{id}/            Delete a saved query
POST   /api/plugins/sqlquery/saved-queries/{id}/execute/    Execute a saved query
```

The API enforces that a user cannot set `owner` to another user. Queries are always created with the requesting user as owner.

### Executing queries via API

Use the `execute` endpoint to run a saved query and get results as JSON:

```bash
curl -X POST \
  -H "Authorization: Token <your-token>" \
  http://localhost/api/plugins/sqlquery/saved-queries/1/execute/
```

For write queries, include `{"confirmed": true}`:

```bash
curl -X POST \
  -H "Authorization: Token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"confirmed": true}' \
  http://localhost/api/plugins/sqlquery/saved-queries/2/execute/
```

The response includes `columns`, `rows`, `row_count`, and `truncated` (for read queries) or `rows_affected` (for write queries). The API token must have write access enabled since the endpoint uses POST. See [operations.md](operations.md) for more details.
