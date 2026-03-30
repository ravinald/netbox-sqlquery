from netbox.plugins import PluginMenu, PluginMenuItem

QUERY_PERMS = ["netbox_sqlquery.view_querypermission"]


def get_menu():
    """Return a top-level PluginMenu for the nav bar."""
    return PluginMenu(
        label="SQL Query",
        groups=(
            (
                "Queries",
                (
                    PluginMenuItem(
                        link="plugins:netbox_sqlquery:query",
                        link_text="SQL Console",
                        permissions=QUERY_PERMS,
                    ),
                    PluginMenuItem(
                        link="plugins:netbox_sqlquery:savedquery_list",
                        link_text="Saved Queries",
                        permissions=QUERY_PERMS,
                    ),
                ),
            ),
        ),
        icon_class="mdi mdi-database-search",
    )


def get_menu_items():
    """Return menu items for the shared Plugins dropdown."""
    return (
        PluginMenuItem(
            link="plugins:netbox_sqlquery:query",
            link_text="SQL Console",
            permissions=QUERY_PERMS,
        ),
        PluginMenuItem(
            link="plugins:netbox_sqlquery:savedquery_list",
            link_text="Saved Queries",
            permissions=QUERY_PERMS,
        ),
    )
