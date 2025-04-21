from django.db import migrations


def create_admin_pw_variable(apps, schema_editor):
    Organization = apps.get_model("odk_publish", "Organization")
    TemplateVariable = apps.get_model("odk_publish", "TemplateVariable")

    org = Organization.objects.order_by("id").first()
    if org:
        TemplateVariable.objects.get_or_create(
            name="admin_pw",
            organization=org,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("odk_publish", "0010_organization_organizationinvitation_and_more"),
    ]

    operations = [
        migrations.RunPython(create_admin_pw_variable, reverse_code=migrations.RunPython.noop),
    ]
