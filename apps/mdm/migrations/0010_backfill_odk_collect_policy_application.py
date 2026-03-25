"""
Data migration: create the pinned ODK Collect PolicyApplication (order=0) for every
existing Policy that doesn't already have one.  This ensures the "ODK Collect is always
first / always present" invariant is upheld for policies created before migration 0009
introduced the PolicyApplication table.
"""

from django.db import migrations


def backfill_odk_collect_application(apps, schema_editor):
    Policy = apps.get_model("mdm", "Policy")
    PolicyApplication = apps.get_model("mdm", "PolicyApplication")
    DEFAULT_PACKAGE = "org.odk.collect.android"

    # Use all_mdms (the plain Manager) rather than objects (PolicyManager) so that policies
    # for all MDM types are backfilled, regardless of the current ACTIVE_MDM setting.
    for policy in Policy.all_mdms.all():
        package_name = getattr(policy, "odk_collect_package", None) or DEFAULT_PACKAGE
        if not PolicyApplication.objects.filter(policy=policy, order=0).exists():
            PolicyApplication.objects.create(
                policy=policy,
                package_name=package_name,
                install_type="FORCE_INSTALLED",
                order=0,
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("mdm", "0009_policyapplication_policyvariable_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_odk_collect_application, reverse_code=noop),
    ]
