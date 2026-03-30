from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory, override_settings

from netbox_sqlquery.views import QueryView


PLUGIN_CONFIG = {
    "netbox_sqlquery": {
        "require_superuser": True,
        "max_rows": 1000,
        "statement_timeout_ms": 10000,
        "deny_tables": ["auth_user", "users_token", "users_userconfig"],
    }
}


@override_settings(PLUGINS_CONFIG=PLUGIN_CONFIG)
class QueryViewAccessTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.superuser = User.objects.create_user(
            "superuser", password="test", is_superuser=True, is_staff=True,
        )
        self.staff_user = User.objects.create_user(
            "staffuser", password="test", is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            "regular", password="test",
        )

    def test_unauthenticated_user_gets_403(self):
        response = self.client.get("/plugins/sqlquery/")
        self.assertIn(response.status_code, [302, 403])

    def test_non_staff_user_gets_403_when_require_superuser_is_true(self):
        self.client.force_login(self.staff_user)
        response = self.client.get("/plugins/sqlquery/")
        self.assertIn(response.status_code, [302, 403])

    def test_superuser_can_access_query_view(self):
        self.client.force_login(self.superuser)
        with patch("netbox_sqlquery.views.get_schema", return_value={}):
            response = self.client.get("/plugins/sqlquery/")
        self.assertEqual(response.status_code, 200)


@override_settings(PLUGINS_CONFIG=PLUGIN_CONFIG)
class QueryViewExecutionTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_user(
            "superuser", password="test", is_superuser=True, is_staff=True,
        )
        self.client.force_login(self.superuser)

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    @patch("netbox_sqlquery.views.connection")
    def test_select_query_executes_and_returns_results(self, mock_conn, mock_schema):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchmany.return_value = [(1, "test")]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        response = self.client.post("/plugins/sqlquery/", {"sql": "SELECT 1"})
        self.assertEqual(response.status_code, 200)

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    def test_insert_statement_is_rejected(self, mock_schema):
        response = self.client.post(
            "/plugins/sqlquery/", {"sql": "INSERT INTO foo VALUES (1)"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only SELECT")

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    def test_update_statement_is_rejected(self, mock_schema):
        response = self.client.post(
            "/plugins/sqlquery/", {"sql": "UPDATE foo SET bar = 1"}
        )
        self.assertContains(response, "Only SELECT")

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    def test_delete_statement_is_rejected(self, mock_schema):
        response = self.client.post(
            "/plugins/sqlquery/", {"sql": "DELETE FROM foo"}
        )
        self.assertContains(response, "Only SELECT")

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    def test_drop_statement_is_rejected(self, mock_schema):
        response = self.client.post(
            "/plugins/sqlquery/", {"sql": "DROP TABLE foo"}
        )
        self.assertContains(response, "Only SELECT")

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    def test_denied_table_returns_error(self, mock_schema):
        response = self.client.post(
            "/plugins/sqlquery/", {"sql": "SELECT * FROM auth_user"}
        )
        self.assertContains(response, "Access denied")

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    @patch("netbox_sqlquery.views.connection")
    def test_max_rows_is_enforced(self, mock_conn, mock_schema):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",)]
        mock_cursor.fetchmany.return_value = [(i,) for i in range(1000)]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        self.client.post("/plugins/sqlquery/", {"sql": "SELECT id FROM dcim_device"})
        mock_cursor.fetchmany.assert_called_with(1000)

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    @patch("netbox_sqlquery.views.connection")
    def test_statement_timeout_is_set(self, mock_conn, mock_schema):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",)]
        mock_cursor.fetchmany.return_value = []
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        self.client.post("/plugins/sqlquery/", {"sql": "SELECT 1"})
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        timeout_set = any("statement_timeout" in c for c in calls)
        self.assertTrue(timeout_set)
