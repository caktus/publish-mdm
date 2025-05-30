# Generated by Django 5.1.5 on 2025-02-28 23:52

from django.db import migrations, models
from django.contrib.postgres.operations import CreateCollation
from django.core.management import CommandError


def check_duplicate_names(apps, schema_editor):
    model = apps.get_model("publish_mdm", "AppUser")
    duplicates = (
        model.objects.values_list(models.functions.Lower("name"), "project")
        .annotate(count=models.Count("*"))
        .filter(count__gt=1)
    )
    if duplicates:
        duplicates = "\n".join(f"  '{i[0]}' in project ID {i[1]}: {i[2]} users" for i in duplicates)
        print()  # Needed so the error message can be shown on its own line
        raise CommandError(
            "There are app users with duplicate names. Either delete or rename "
            f"the duplicates before rerunning this migration:\n{duplicates}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("publish_mdm", "0002_alter_appuser_central_id"),
    ]

    operations = [
        migrations.RunPython(check_duplicate_names, migrations.RunPython.noop),
        CreateCollation(
            "case_insensitive",
            provider="icu",
            locale="und-u-ks-level2",
            deterministic=False,
        ),
        migrations.AlterField(
            model_name="appuser",
            name="name",
            field=models.CharField(db_collation="case_insensitive", max_length=255),
        ),
    ]
