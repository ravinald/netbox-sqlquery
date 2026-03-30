from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from users.models import Group

from netbox_sqlquery.access import (
    ALL_TABLES,
    SHARED_TABLES,
    _allowed_tables,
    check_access,
    extract_tables,
)
from netbox_sqlquery.models import TablePermission

User = get_user_model()

PLUGIN_CONFIG = {
    "netbox_sqlquery": {
        "deny_tables": ["auth_user", "users_token", "users_userconfig"],
    }
}


class ExtractTablesTest(TestCase):
    def test_extract_tables_finds_from_clause(self):
        sql = "SELECT * FROM dcim_device WHERE id = 1"
        self.assertEqual(extract_tables(sql), {"dcim_device"})

    def test_extract_tables_finds_join_clause(self):
        sql = "SELECT * FROM dcim_device JOIN dcim_site ON dcim_device.site_id = dcim_site.id"
        self.assertEqual(extract_tables(sql), {"dcim_device", "dcim_site"})

    def test_extract_tables_handles_cte(self):
        sql = "WITH cte AS (SELECT * FROM dcim_device) SELECT * FROM cte"
        tables = extract_tables(sql)
        self.assertIn("dcim_device", tables)
        self.assertIn("cte", tables)


@override_settings(PLUGINS_CONFIG=PLUGIN_CONFIG)
class CheckAccessTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            "superuser",
            password="test",
            is_superuser=True,
        )
        self.staff_user = User.objects.create_user(
            "staffuser",
            password="test",
        )
        self.regular_user = User.objects.create_user(
            "regular",
            password="test",
        )
        self.group = Group.objects.create(name="network_team")

    def test_superuser_can_access_all_tables(self):
        result = _allowed_tables(self.superuser)
        self.assertIs(result, ALL_TABLES)

    def test_hard_deny_blocks_superuser(self):
        denied = check_access(self.superuser, {"auth_user", "dcim_device"})
        self.assertEqual(denied, {"auth_user"})

    def test_staff_tier_default_allows_dcim_tables(self):
        TablePermission.objects.create(
            pattern="dcim_",
            scope=TablePermission.SCOPE_PREFIX,
            require_staff=True,
            allow=True,
        )
        allowed = _allowed_tables(self.staff_user)
        self.assertIn("dcim_", allowed)

    def test_regular_user_gets_only_shared_tables(self):
        allowed = _allowed_tables(self.regular_user)
        self.assertEqual(allowed, SHARED_TABLES)

    def test_group_override_expands_access_for_group_member(self):
        self.regular_user.groups.add(self.group)
        perm = TablePermission.objects.create(
            pattern="ipam_",
            scope=TablePermission.SCOPE_PREFIX,
            allow=True,
        )
        perm.groups.add(self.group)
        allowed = _allowed_tables(self.regular_user)
        self.assertIn("ipam_", allowed)

    def test_explicit_deny_in_table_permission_overrides_allow(self):
        self.staff_user.groups.add(self.group)
        TablePermission.objects.create(
            pattern="dcim_",
            scope=TablePermission.SCOPE_PREFIX,
            require_staff=True,
            allow=True,
        )
        deny_perm = TablePermission.objects.create(
            pattern="dcim_",
            scope=TablePermission.SCOPE_PREFIX,
            allow=False,
        )
        deny_perm.groups.add(self.group)
        allowed = _allowed_tables(self.staff_user)
        self.assertNotIn("dcim_", allowed)

    def test_wildcard_prefix_matches_all_prefixed_tables(self):
        perm = TablePermission(pattern="dcim_", scope=TablePermission.SCOPE_PREFIX)
        self.assertTrue(perm.matches("dcim_device"))
        self.assertTrue(perm.matches("dcim_site"))
        self.assertFalse(perm.matches("ipam_ipaddress"))
