import logging

from netbox.plugins import PluginConfig

logger = logging.getLogger("netbox_sqlquery")


class NetBoxSQLQueryConfig(PluginConfig):
    name = "netbox_sqlquery"
    verbose_name = "SQL Query Explorer"
    description = (
        "SQL query interface for NetBox with syntax highlighting,"
        " abstract views, and role-based access control"
    )
    version = "0.1.7"
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
        "ai_enabled": False,
        "ai_provider": "openai",
        "ai_model": "",
        "ai_base_url": "",
        "ai_api_key": "",
        "ai_temperature": 0.0,
        "ai_max_tokens": 1024,
        "ai_timeout": 30,
        "ai_system_context": "",
    }

    # Suppress auto-loading; we register navigation conditionally in ready()
    menu = None
    menu_items = None

    def ready(self):
        super().ready()

        # Register navigation based on top_level_menu setting
        self._register_navigation()

        # Drop views before migrations so PostgreSQL can alter columns
        # that the views depend on. Recreate them after migrations
        # complete against the new schema. The views are read-only
        # projections and contain no data, so this is always safe.
        from django.db.models.signals import post_migrate, pre_migrate

        pre_migrate.connect(self._drop_views, sender=self)
        post_migrate.connect(self._create_views_forced, sender=self)

        # For normal app startup (gunicorn/uvicorn), skip expensive view
        # creation if views already exist — just populate the table map.
        self._create_views(sender=self)

    @staticmethod
    def _drop_views(sender, **kwargs):
        try:
            from .abstract_schema import drop_views

            dropped = drop_views()
            if dropped:
                logger.info(
                    "Dropped %d abstract SQL view(s) before migration.",
                    len(dropped),
                )
        except Exception as exc:
            logger.warning("Could not drop abstract SQL views: %s", exc)

    @staticmethod
    def _create_views(sender, **kwargs):
        """Normal startup — skips creation if views already exist."""
        try:
            from .abstract_schema import ensure_views

            ensure_views()  # force=False: fast path when views exist
        except Exception as exc:
            logger.warning(
                "Could not create abstract SQL views: %s. "
                "Run 'manage.py sqlquery_create_views' manually.",
                exc,
            )

    @staticmethod
    def _create_views_forced(sender, **kwargs):
        """Post-migrate — always rebuild views against the new schema."""
        try:
            from .abstract_schema import ensure_views

            ensure_views(force=True)
        except Exception as exc:
            logger.warning(
                "Could not create abstract SQL views after migration: %s. "
                "Run 'manage.py sqlquery_create_views --force' manually.",
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
