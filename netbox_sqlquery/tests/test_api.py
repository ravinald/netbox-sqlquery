from django.contrib.auth import get_user_model
from django.test import TestCase

from netbox_sqlquery.models import SavedQuery

User = get_user_model()


class SavedQueryModelAPITest(TestCase):
    """Test SavedQuery visibility logic at the model level."""

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

    def test_list_returns_only_owned_and_global_queries(self):
        visible = SavedQuery.visible_to(self.user2)
        names = list(visible.values_list("name", flat=True))
        self.assertIn("Global", names)
        self.assertNotIn("Private", names)

    def test_owner_sees_own_private_queries(self):
        visible = SavedQuery.visible_to(self.user1)
        names = list(visible.values_list("name", flat=True))
        self.assertIn("Private", names)
        self.assertIn("Global", names)

    def test_visibility_choices_are_valid(self):
        valid = dict(SavedQuery.VISIBILITY_CHOICES).keys()
        self.assertIn(SavedQuery.VISIBILITY_PRIVATE, valid)
        self.assertIn(SavedQuery.VISIBILITY_GLOBAL, valid)
        self.assertIn(SavedQuery.VISIBILITY_GLOBAL_EDITABLE, valid)
