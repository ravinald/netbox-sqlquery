from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_sqlquery", "0002_query_permissions"),
        ("users", "0001_squashed_0011"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tablepermission",
            name="groups",
            field=models.ManyToManyField(blank=True, to="users.group"),
        ),
    ]
