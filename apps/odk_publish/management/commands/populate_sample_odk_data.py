import logging

from django.core.management.base import BaseCommand
from django.db import transaction

import apps.odk_publish.models as odk_publish

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    @transaction.atomic
    def handle(self, *args, **options):
        logger.info("Cleaning data...")
        odk_publish.CentralServer.objects.all().delete()
        odk_publish.Project.objects.all().delete()
        odk_publish.FormTemplate.objects.all().delete()
        logger.info("Creating CentralServer...")
        central_server = odk_publish.CentralServer.objects.create(
            base_url="https://odk-central.caktustest.net/"
        )
        logger.info("Creating Project...")
        project = odk_publish.Project.objects.create(
            name="Caktus Test",
            project_id=1,
            central_server=central_server,
        )
        logger.info("Creating FormTemplate...")
        odk_publish.FormTemplate.objects.create(
            title_base="Staff Registration",
            form_id_base="staff_registration_center",
            template_url="https://docs.google.com/spreadsheets/d/1Qu5lVRBDMvkmcYEJWbpousaHZYuXM3cY_X5rNasrmys/edit",
            project=project,
        )
