from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("mdm", "0014_enrollmenttoken"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="enrollmenttoken",
            name="mdm",
        ),
    ]
