from django.core.cache import cache
from django.db import connection

SCHEMA_CACHE_KEY = "netbox_sqlquery_schema"
ABSTRACT_SCHEMA_CACHE_KEY = "netbox_sqlquery_abstract_schema"
SCHEMA_CACHE_TTL = 300


def get_schema():
    cached = cache.get(SCHEMA_CACHE_KEY)
    if cached is not None:
        return cached

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT t.table_name, c.column_name, c.data_type
            FROM information_schema.tables t
            JOIN information_schema.columns c
              ON t.table_name = c.table_name
             AND t.table_schema = c.table_schema
            WHERE t.table_schema = 'public'
              AND t.table_type = 'BASE TABLE'
            ORDER BY t.table_name, c.ordinal_position
        """)
        schema = {}
        for table, column, dtype in cursor.fetchall():
            schema.setdefault(table, []).append((column, dtype))

    cache.set(SCHEMA_CACHE_KEY, schema, SCHEMA_CACHE_TTL)
    return schema


def get_abstract_schema():
    """Return schema for abstract (nb_*) views only."""
    cached = cache.get(ABSTRACT_SCHEMA_CACHE_KEY)
    if cached is not None:
        return cached

    with connection.cursor() as cursor:
        cursor.execute(r"""
            SELECT c.table_name, c.column_name, c.data_type
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
              AND c.table_name LIKE 'nb\_%'
            ORDER BY c.table_name, c.ordinal_position
        """)
        schema = {}
        for table, column, dtype in cursor.fetchall():
            schema.setdefault(table, []).append((column, dtype))

    cache.set(ABSTRACT_SCHEMA_CACHE_KEY, schema, SCHEMA_CACHE_TTL)
    return schema
