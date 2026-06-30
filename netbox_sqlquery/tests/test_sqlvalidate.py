from django.test import SimpleTestCase

from netbox_sqlquery.sqlvalidate import (
    SQLGLOT_AVAILABLE,
    is_read_only_select,
    statement_tables,
    unknown_columns,
)

SCHEMA = {
    "nb_devices": [("name", "text"), ("site", "text"), ("tenant", "text")],
    "nb_sites": [("name", "text"), ("facility", "text")],
}


class IsReadOnlySelectTest(SimpleTestCase):
    def test_accepts_plain_select(self):
        self.assertTrue(is_read_only_select("SELECT * FROM nb_devices"))

    def test_accepts_cte_and_union(self):
        self.assertTrue(
            is_read_only_select("WITH c AS (SELECT * FROM nb_devices) SELECT * FROM c")
        )
        self.assertTrue(
            is_read_only_select("SELECT a FROM nb_devices UNION SELECT a FROM nb_sites")
        )

    def test_rejects_dml_and_ddl(self):
        for sql in (
            "DELETE FROM dcim_device",
            "UPDATE dcim_device SET name='x'",
            "INSERT INTO dcim_device (name) VALUES ('x')",
            "DROP VIEW nb_devices",
            "TRUNCATE dcim_device",
        ):
            self.assertFalse(is_read_only_select(sql), sql)

    def test_rejects_multi_statement(self):
        self.assertFalse(is_read_only_select("SELECT 1; DROP TABLE dcim_device"))

    def test_rejects_data_modifying_cte(self):
        sql = "WITH t AS (DELETE FROM dcim_device RETURNING *) SELECT * FROM t"
        self.assertFalse(is_read_only_select(sql))

    def test_rejects_empty(self):
        self.assertFalse(is_read_only_select(""))


class StatementTablesTest(SimpleTestCase):
    def test_from_and_join(self):
        sql = "SELECT * FROM dcim_device JOIN dcim_site ON dcim_device.site_id = dcim_site.id"
        self.assertEqual(statement_tables(sql), {"dcim_device", "dcim_site"})

    def test_includes_cte_name(self):
        tables = statement_tables("WITH cte AS (SELECT * FROM dcim_device) SELECT * FROM cte")
        self.assertIn("dcim_device", tables)
        self.assertIn("cte", tables)

    def test_returns_none_on_unparseable(self):
        # Multi-statement input is treated as unparseable -> signal regex fallback.
        self.assertIsNone(statement_tables("DROP TABLE x; DROP TABLE y"))


class UnknownColumnsTest(SimpleTestCase):
    def test_no_unknowns_for_valid_query(self):
        self.assertEqual(unknown_columns("SELECT name, site FROM nb_devices", SCHEMA), [])

    def test_flags_qualified_unknown_column(self):
        self.assertEqual(
            unknown_columns("SELECT d.sit FROM nb_devices d", SCHEMA), ["nb_devices.sit"]
        )

    def test_flags_unqualified_unknown_on_single_table(self):
        self.assertEqual(
            unknown_columns("SELECT bogus FROM nb_devices", SCHEMA), ["nb_devices.bogus"]
        )

    def test_skips_ambiguous_unqualified(self):
        self.assertEqual(unknown_columns("SELECT name FROM nb_devices, nb_sites", SCHEMA), [])

    def test_skips_cte_columns(self):
        sql = "WITH c AS (SELECT name FROM nb_devices) SELECT whatever FROM c"
        self.assertEqual(unknown_columns(sql, SCHEMA), [])

    def test_catches_qualified_unknown_in_join(self):
        sql = "SELECT d.nope, s.facility FROM nb_devices d JOIN nb_sites s ON d.site = s.name"
        self.assertEqual(unknown_columns(sql, SCHEMA), ["nb_devices.nope"])


class SqlglotAvailableTest(SimpleTestCase):
    def test_sqlglot_is_installed(self):
        # sqlglot is a declared dependency; the AST-backed guards rely on it.
        self.assertTrue(SQLGLOT_AVAILABLE)
