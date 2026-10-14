import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_sqlquery", "0003_nlexample"),
    ]

    operations = [
        migrations.AlterField(
            model_name="savedquery",
            name="name",
            field=models.CharField(
                max_length=100,
                validators=[
                    django.core.validators.RegexValidator(
                        message=(
                            "Name must start with a letter or number and contain only"
                            " letters, numbers, spaces, hyphens, underscores, and periods."
                        ),
                        regex="^[a-zA-Z0-9][a-zA-Z0-9 _\\-\\.]*$",
                    )
                ],
            ),
        ),
    ]
