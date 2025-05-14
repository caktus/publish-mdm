import structlog
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

import apps.publish_mdm.models as publish_mdm

logger = structlog.getLogger(__name__)


class Command(BaseCommand):
    @transaction.atomic
    def handle(self, *args, **options):
        logger.info("Cleaning data...")
        publish_mdm.Organization.objects.all().delete()
        publish_mdm.CentralServer.objects.all().delete()
        publish_mdm.TemplateVariable.objects.all().delete()
        publish_mdm.Project.objects.all().delete()
        publish_mdm.FormTemplate.objects.all().delete()
        publish_mdm.AppUser.objects.all().delete()
        logger.info("Cleaning downloaded templates...")
        downloaded_templates = Path(settings.MEDIA_ROOT) / "form-templates"
        for file in downloaded_templates.glob("*"):
            if file.is_file():
                logger.info("Removing file", file=file.name)
                file.unlink()
        logger.info("Creating Organization...")
        organization = publish_mdm.Organization.objects.create(name="Caktus Group", slug="caktus")
        logger.info("Creating CentralServers...")
        central_server = publish_mdm.CentralServer.objects.create(
            base_url="https://odk-central.caktustest.net/",
            organization=organization,
        )
        myodkcloud = publish_mdm.CentralServer.objects.create(
            base_url="https://myodkcloud.com/", organization=organization
        )
        logger.info("Creating Projects...")
        project = publish_mdm.Project.objects.create(
            name="Caktus Test",
            central_id=1,
            central_server=central_server,
            organization=organization,
        )
        publish_mdm.Project.objects.create(
            name="Other Project",
            central_id=5,
            central_server=myodkcloud,
            organization=organization,
        )
        logger.info("Creating TemplateVariable...")
        center_id_var = publish_mdm.TemplateVariable.objects.create(
            name="center_id", organization=organization
        )
        center_label_var = publish_mdm.TemplateVariable.objects.create(
            name="center_label", organization=organization
        )
        public_key_var = publish_mdm.TemplateVariable.objects.create(
            name="public_key", organization=organization
        )
        manager_password_var = publish_mdm.TemplateVariable.objects.create(
            name="manager_password", organization=organization
        )
        project.template_variables.set(
            [center_id_var, center_label_var, public_key_var, manager_password_var]
        )
        logger.info("Creating FormTemplate...")
        publish_mdm.FormTemplate.objects.create(
            title_base="Staff Registration",
            form_id_base="staff_registration_center",
            template_url="https://docs.google.com/spreadsheets/d/1Qu5lVRBDMvkmcYEJWbpousaHZYuXM3cY_X5rNasrmys/edit",
            project=project,
        )
        logger.info("Creating AppUser...")
        for center_id in ["11030", "11035"]:
            app_user = publish_mdm.AppUser.objects.create(
                name=center_id,
                project=project,
                central_id=1,
            )
            publish_mdm.AppUserTemplateVariable.objects.create(
                app_user=app_user, template_variable=center_id_var, value=center_id
            )
            publish_mdm.AppUserTemplateVariable.objects.create(
                app_user=app_user, template_variable=center_label_var, value=f"Center {center_id}"
            )
            publish_mdm.AppUserTemplateVariable.objects.create(
                app_user=app_user, template_variable=public_key_var, value="mykey"
            )
            publish_mdm.AppUserTemplateVariable.objects.create(
                app_user=app_user, template_variable=manager_password_var, value="abc123"
            )
        logger.info("Creating AppUserFormTemplate...")
        for app_user in publish_mdm.AppUser.objects.all():
            for form_template in publish_mdm.FormTemplate.objects.all():
                publish_mdm.AppUserFormTemplate.objects.create(
                    app_user=app_user, form_template=form_template
                )
