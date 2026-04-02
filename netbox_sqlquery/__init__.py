import logging
import sys

from netbox.plugins import PluginConfig

logger = logging.getLogger("netbox_sqlquery")

# Management commands that modify schema — creating views during these
# can block migrations when a view depends on a column being altered.
_SKIP_VIEWS_COMMANDS = {"migrate", "makemigrations"}


class NetBoxSQLQueryConfig(PluginConfig):
    name = "netbox_sqlquery"
    verbose_name = "SQL Query Explorer"
    description = (
        "SQL query interface for NetBox with syntax highlighting,"
        " abstract views, and role-based access control"
    )
    version = "0.1.5"
    author = "Ravi Pina"
    author_email = "ravi@pina.org"
    base_url = "sqlquery"
    min_version = "4.5.0"
    max_version = None
    required_settings = []
    default_settings = {
        "require_superuser": True,
        "max_rows": 1000,
        "statement_timeout_ms": 10_000,
        "deny_tables": [
            "auth_user",
            "users_token",
            "users_userconfig",
        ],
        "top_level_menu": False,
    }

    # Suppress auto-loading; we register navigation conditionally in ready()
    menu = None
    menu_items = None

    def ready(self):
        super().ready()

        # Register navigation based on top_level_menu setting
        self._register_navigation()

        # Hook post_migrate so views are (re)created after schema changes.
        from django.db.models.signals import post_migrate

        post_migrate.connect(self._create_views, sender=self)

        # For normal app startup (gunicorn/uvicorn), create views directly.
        # Skip during management commands that modify schema — views that
        # reference columns being altered will cause PostgreSQL to reject
        # the migration with "cannot alter type of a column used by a view".
        running_command = sys.argv[1] if len(sys.argv) > 1 else None
        if running_command not in _SKIP_VIEWS_COMMANDS:
            self._create_views(sender=self)

    @staticmethod
    def _create_views(sender, **kwargs):
        try:
            from .abstract_schema import ensure_views

            ensure_views()
        except Exception as exc:
            logger.warning(
                "Could not create abstract SQL views: %s. "
                "Run 'manage.py sqlquery_create_views' manually.",
                exc,
            )

    def _register_navigation(self):
        from netbox.plugins.registration import register_menu, register_menu_items

        from .navigation import get_menu, get_menu_items

        try:
            from netbox.plugins import get_plugin_config

            top_level = get_plugin_config("netbox_sqlquery", "top_level_menu")
        except Exception:
            top_level = False

        if top_level:
            register_menu(get_menu())
        else:
            register_menu_items(self.verbose_name, get_menu_items())


config = NetBoxSQLQueryConfig
