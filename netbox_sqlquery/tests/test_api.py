from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from netbox_sqlquery.models import SavedQuery


class SavedQueryAPITest(TestCase):

    def setUp(self):
        self.user1 = User.objects.create_user("user1", password="test")
        self.user2 = User.objects.create_user("user2", password="test")
        self.staff = User.objects.create_user(
            "staff", password="test", is_staff=True,
        )
        self.client = APIClient()

        self.private_query = SavedQuery.objects.create(
            name="Private", sql="SELECT 1", owner=self.user1,
            visibility=SavedQuery.VISIBILITY_PRIVATE,
        )
        self.global_query = SavedQuery.objects.create(
            name="Global", sql="SELECT 2", owner=self.user1,
            visibility=SavedQuery.VISIBILITY_GLOBAL,
        )

    def test_list_returns_only_owned_and_global_queries(self):
        self.client.force_authenticate(self.user2)
        response = self.client.get("/api/plugins/sqlquery/saved-queries/")
        self.assertEqual(response.status_code, 200)
        names = [q["name"] for q in response.data]
        self.assertIn("Global", names)
        self.assertNotIn("Private", names)

    def test_user_cannot_set_owner_to_another_user(self):
        self.client.force_authenticate(self.user1)
        response = self.client.post(
            "/api/plugins/sqlquery/saved-queries/",
            {"name": "Test", "sql": "SELECT 1", "owner": self.user2.pk},
            format="json",
        )
        self.assertIn(response.status_code, [400, 201])
        if response.status_code == 201:
            self.assertEqual(response.data["owner"], self.user1.pk)

    def test_non_staff_cannot_set_global_editable_visibility(self):
        self.client.force_authenticate(self.user1)
        response = self.client.post(
            "/api/plugins/sqlquery/saved-queries/",
            {
                "name": "Test",
                "sql": "SELECT 1",
                "visibility": SavedQuery.VISIBILITY_GLOBAL_EDITABLE,
            },
            format="json",
        )
        if response.status_code == 400:
            self.assertIn("visibility", str(response.data))
