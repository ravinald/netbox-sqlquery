import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("extras", "0001_initial"),
        ("users", "0001_squashed_0011"),
    ]

    operations = [
        migrations.CreateModel(
            name="SavedQuery",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("description", models.CharField(blank=True, max_length=256)),
                ("sql", models.TextField()),
                (
                    "visibility",
                    models.CharField(
                        choices=[
                            ("private", "Private"),
                            ("global", "Global (read-only)"),
                            ("global_editable", "Global (editable by staff)"),
                        ],
                        default="private",
                        max_length=20,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("last_run", models.DateTimeField(null=True, blank=True)),
                ("run_count", models.PositiveIntegerField(default=0)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="saved_queries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("tags", models.ManyToManyField(blank=True, to="extras.tag")),
            ],
            options={
                "ordering": ["name"],
                "verbose_name_plural": "saved queries",
            },
        ),
        migrations.CreateModel(
            name="TablePermission",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("pattern", models.CharField(max_length=100)),
                (
                    "scope",
                    models.CharField(
                        choices=[
                            ("exact", "Exact table name"),
                            ("prefix", "Table prefix (e.g. dcim_)"),
                        ],
                        default="exact",
                        max_length=10,
                    ),
                ),
                ("require_staff", models.BooleanField(default=False)),
                ("require_superuser", models.BooleanField(default=False)),
                ("allow", models.BooleanField(default=True)),
                ("groups", models.ManyToManyField(blank=True, to="users.group")),
            ],
            options={
                "ordering": ["-require_superuser", "-require_staff", "pattern"],
            },
        ),
    ]
