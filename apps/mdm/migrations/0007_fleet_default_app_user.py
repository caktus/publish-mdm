import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mdm", "0006_remove_policy_unique_default_policy_and_more"),
        ("publish_mdm", "0014_organization_public_signup_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="fleet",
            name="default_app_user",
            field=models.ForeignKey(
                blank=True,
                help_text="If set, newly enrolled devices are automatically assigned this app user.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="default_fleet_set",
                to="publish_mdm.appuser",
            ),
        ),
    ]
