from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

User = get_user_model()

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
        self.superuser = User.objects.create_user(
            "superuser", password="test", is_superuser=True,
        )
        self.regular_user = User.objects.create_user(
            "regular", password="test",
        )

    def test_unauthenticated_user_gets_403(self):
        response = self.client.get("/plugins/sqlquery/")
        self.assertIn(response.status_code, [302, 403])

    def test_non_superuser_gets_403_when_require_superuser_is_true(self):
        self.client.force_login(self.regular_user)
        response = self.client.get("/plugins/sqlquery/")
        self.assertIn(response.status_code, [302, 403])

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    @patch("netbox_sqlquery.views.get_abstract_schema", return_value={})
    def test_superuser_can_access_query_view(self, mock_abs, mock_schema):
        self.client.force_login(self.superuser)
        response = self.client.get("/plugins/sqlquery/")
        self.assertEqual(response.status_code, 200)


@override_settings(PLUGINS_CONFIG=PLUGIN_CONFIG)
class QueryViewExecutionTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_user(
            "superuser", password="test", is_superuser=True,
        )
        self.client.force_login(self.superuser)

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    @patch("netbox_sqlquery.views.get_abstract_schema", return_value={})
    def test_insert_statement_allowed_for_superuser(self, mock_abs, mock_schema):
        response = self.client.post(
            "/plugins/sqlquery/", {"sql": "INSERT INTO foo VALUES (1)"}
        )
        self.assertEqual(response.status_code, 200)

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    @patch("netbox_sqlquery.views.get_abstract_schema", return_value={})
    def test_drop_statement_is_rejected(self, mock_abs, mock_schema):
        response = self.client.post(
            "/plugins/sqlquery/", {"sql": "DROP TABLE foo"}
        )
        self.assertContains(response, "Only SELECT")

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    @patch("netbox_sqlquery.views.get_abstract_schema", return_value={})
    def test_denied_table_returns_error(self, mock_abs, mock_schema):
        response = self.client.post(
            "/plugins/sqlquery/", {"sql": "SELECT * FROM auth_user"}
        )
        self.assertContains(response, "Access denied")

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    @patch("netbox_sqlquery.views.get_abstract_schema", return_value={})
    def test_empty_sql_returns_error(self, mock_abs, mock_schema):
        response = self.client.post(
            "/plugins/sqlquery/", {"sql": ""}
        )
        self.assertContains(response, "No SQL provided")

    @patch("netbox_sqlquery.views.get_schema", return_value={})
    @patch("netbox_sqlquery.views.get_abstract_schema", return_value={})
    def test_select_query_returns_200(self, mock_abs, mock_schema):
        response = self.client.post(
            "/plugins/sqlquery/", {"sql": "SELECT 1"}
        )
        self.assertEqual(response.status_code, 200)
