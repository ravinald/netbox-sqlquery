from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_sqlquery", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="QueryPermission",
            fields=[],
            options={
                "managed": False,
                "default_permissions": ("view", "change"),
                "verbose_name": "SQL query permission",
                "verbose_name_plural": "SQL query permissions",
            },
        ),
    ]
