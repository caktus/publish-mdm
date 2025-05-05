import structlog
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

import apps.odk_publish.models as odk_publish

logger = structlog.getLogger(__name__)


class Command(BaseCommand):
    @transaction.atomic
    def handle(self, *args, **options):
        logger.info("Cleaning data...")
        odk_publish.Organization.objects.all().delete()
        odk_publish.CentralServer.objects.all().delete()
        odk_publish.TemplateVariable.objects.all().delete()
        odk_publish.Project.objects.all().delete()
        odk_publish.FormTemplate.objects.all().delete()
        odk_publish.AppUser.objects.all().delete()
        logger.info("Cleaning downloaded templates...")
        downloaded_templates = Path(settings.MEDIA_ROOT) / "form-templates"
        for file in downloaded_templates.glob("*"):
            if file.is_file():
                logger.info("Removing file", file=file.name)
                file.unlink()
        logger.info("Creating Organization...")
        organization = odk_publish.Organization.objects.create(name="Caktus Group", slug="caktus")
        logger.info("Creating CentralServers...")
        central_server = odk_publish.CentralServer.objects.create(
            base_url="https://odk-central.caktustest.net/",
            organization=organization,
        )
        myodkcloud = odk_publish.CentralServer.objects.create(
            base_url="https://myodkcloud.com/", organization=organization
        )
        logger.info("Creating Projects...")
        project = odk_publish.Project.objects.create(
            name="Caktus Test",
            central_id=1,
            central_server=central_server,
            organization=organization,
        )
        odk_publish.Project.objects.create(
            name="Other Project",
            central_id=5,
            central_server=myodkcloud,
            organization=organization,
        )
        logger.info("Creating TemplateVariable...")
        center_id_var = odk_publish.TemplateVariable.objects.create(
            name="center_id", organization=organization
        )
        center_label_var = odk_publish.TemplateVariable.objects.create(
            name="center_label", organization=organization
        )
        public_key_var = odk_publish.TemplateVariable.objects.create(
            name="public_key", organization=organization
        )
        manager_password_var = odk_publish.TemplateVariable.objects.create(
            name="manager_password", organization=organization
        )
        project.template_variables.set(
            [center_id_var, center_label_var, public_key_var, manager_password_var]
        )
        logger.info("Creating FormTemplate...")
        odk_publish.FormTemplate.objects.create(
            title_base="Staff Registration",
            form_id_base="staff_registration_center",
            template_url="https://docs.google.com/spreadsheets/d/1Qu5lVRBDMvkmcYEJWbpousaHZYuXM3cY_X5rNasrmys/edit",
            project=project,
        )
        logger.info("Creating AppUser...")
        for center_id in ["11030", "11035"]:
            app_user = odk_publish.AppUser.objects.create(
                name=center_id,
                project=project,
                central_id=1,
            )
            odk_publish.AppUserTemplateVariable.objects.create(
                app_user=app_user, template_variable=center_id_var, value=center_id
            )
            odk_publish.AppUserTemplateVariable.objects.create(
                app_user=app_user, template_variable=center_label_var, value=f"Center {center_id}"
            )
            odk_publish.AppUserTemplateVariable.objects.create(
                app_user=app_user, template_variable=public_key_var, value="mykey"
            )
            odk_publish.AppUserTemplateVariable.objects.create(
                app_user=app_user, template_variable=manager_password_var, value="abc123"
            )
        logger.info("Creating AppUserFormTemplate...")
        for app_user in odk_publish.AppUser.objects.all():
            for form_template in odk_publish.FormTemplate.objects.all():
                odk_publish.AppUserFormTemplate.objects.create(
                    app_user=app_user, form_template=form_template
                )
