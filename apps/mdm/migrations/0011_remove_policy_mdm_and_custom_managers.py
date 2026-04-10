from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("mdm", "0010_device_manufacturer_model"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="policy",
            name="mdm",
        ),
        migrations.AlterModelManagers(
            name="device",
            managers=[],
        ),
        migrations.AlterModelManagers(
            name="devicesnapshot",
            managers=[],
        ),
        migrations.AlterModelManagers(
            name="firmwaresnapshot",
            managers=[],
        ),
        migrations.AlterModelManagers(
            name="fleet",
            managers=[],
        ),
        migrations.AlterModelManagers(
            name="policy",
            managers=[],
        ),
    ]
