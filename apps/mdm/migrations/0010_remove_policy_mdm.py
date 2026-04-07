from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("mdm", "0009_feature_policy_editor"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="policy",
            name="mdm",
        ),
    ]
