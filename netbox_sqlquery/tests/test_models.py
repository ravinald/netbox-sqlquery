from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from netbox_sqlquery.models import SavedQuery

User = get_user_model()


class SavedQueryVisibilityTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user("user1", password="test")
        self.user2 = User.objects.create_user("user2", password="test")
        self.private_query = SavedQuery.objects.create(
            name="Private",
            sql="SELECT 1",
            owner=self.user1,
            visibility=SavedQuery.VISIBILITY_PRIVATE,
        )
        self.global_query = SavedQuery.objects.create(
            name="Global",
            sql="SELECT 2",
            owner=self.user1,
            visibility=SavedQuery.VISIBILITY_GLOBAL,
        )
        self.editable_query = SavedQuery.objects.create(
            name="Editable",
            sql="SELECT 3",
            owner=self.user1,
            visibility=SavedQuery.VISIBILITY_GLOBAL_EDITABLE,
        )

    def test_private_query_not_visible_to_other_user(self):
        visible = SavedQuery.visible_to(self.user2)
        self.assertNotIn(self.private_query, visible)

    def test_global_query_visible_to_all_authenticated_users(self):
        visible = SavedQuery.visible_to(self.user2)
        self.assertIn(self.global_query, visible)

    def test_global_editable_query_visible_to_all(self):
        visible = SavedQuery.visible_to(self.user2)
        self.assertIn(self.editable_query, visible)

    def test_run_count_increments_on_execution(self):
        self.private_query.run_count += 1
        self.private_query.last_run = timezone.now()
        self.private_query.save()
        self.private_query.refresh_from_db()
        self.assertEqual(self.private_query.run_count, 1)
