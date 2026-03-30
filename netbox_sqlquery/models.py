
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from utilities.querysets import RestrictedQuerySet

SAFE_NAME_VALIDATOR = RegexValidator(
    regex=r'^[a-zA-Z0-9][a-zA-Z0-9 _\-\.]*$',
    message=(
        "Name must start with a letter or number and contain only"
        " letters, numbers, spaces, hyphens, underscores, and periods."
    ),
)


class SavedQuery(models.Model):
    VISIBILITY_PRIVATE = "private"
    VISIBILITY_GLOBAL = "global"
    VISIBILITY_GLOBAL_EDITABLE = "global_editable"

    VISIBILITY_CHOICES = [
        (VISIBILITY_PRIVATE, "Private"),
        (VISIBILITY_GLOBAL, "Global (read-only)"),
        (VISIBILITY_GLOBAL_EDITABLE, "Global (editable by staff)"),
    ]

    name = models.CharField(max_length=100, validators=[SAFE_NAME_VALIDATOR])
    description = models.CharField(max_length=256, blank=True)
    sql = models.TextField()
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_queries",
    )
    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default=VISIBILITY_PRIVATE,
    )
    created = models.DateTimeField(auto_now_add=True)
    last_run = models.DateTimeField(null=True, blank=True)
    run_count = models.PositiveIntegerField(default=0)
    tags = models.ManyToManyField("extras.Tag", blank=True)

    objects = RestrictedQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "saved queries"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("plugins:netbox_sqlquery:savedquery", kwargs={"pk": self.pk})

    @staticmethod
    def visible_to(user):
        return SavedQuery.objects.filter(
            models.Q(owner=user) | ~models.Q(visibility=SavedQuery.VISIBILITY_PRIVATE)
        )


class TablePermission(models.Model):
    SCOPE_EXACT = "exact"
    SCOPE_PREFIX = "prefix"

    SCOPE_CHOICES = [
        (SCOPE_EXACT, "Exact table name"),
        (SCOPE_PREFIX, "Table prefix (e.g. dcim_)"),
    ]

    pattern = models.CharField(max_length=100)
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default=SCOPE_EXACT)
    groups = models.ManyToManyField("users.Group", blank=True)
    require_staff = models.BooleanField(default=False)
    require_superuser = models.BooleanField(default=False)
    allow = models.BooleanField(default=True)

    class Meta:
        ordering = ["-require_superuser", "-require_staff", "pattern"]

    def __str__(self):
        action = "Allow" if self.allow else "Deny"
        return f"{action} {self.get_scope_display()}: {self.pattern}"

    def matches(self, table_name):
        if self.scope == self.SCOPE_EXACT:
            return self.pattern == table_name
        return table_name.startswith(self.pattern)


class QueryPermission(models.Model):
    """Proxy model to register plugin permissions with NetBox's ObjectPermission system.

    Admins assign permissions on this object type:
    - view: Can access the SQL query editor
    - change: Can execute write queries (INSERT/UPDATE/DELETE)
    """

    class Meta:
        managed = False
        default_permissions = ("view", "change")
        verbose_name = "SQL query permission"
        verbose_name_plural = "SQL query permissions"
