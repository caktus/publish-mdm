import structlog
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import QuerySet

from ..models import AppUser, AppUserFormTemplate, FormTemplate, Project
from .odk.client import ODKPublishClient
from .odk.qrcode import create_app_user_qrcode

logger = structlog.getLogger(__name__)


def create_or_update_app_users(form_template: FormTemplate):
    """Create or update app users for the form template."""
    app_user_forms: QuerySet[AppUserFormTemplate] = form_template.app_user_forms.select_related()

    with ODKPublishClient.new_client(
        base_url=form_template.project.central_server.base_url
    ) as client:
        app_users = client.odk_publish.get_or_create_app_users(
            display_names=[app_user_form.app_user.name for app_user_form in app_user_forms],
            project_id=form_template.project.project_id,
        )
        # Link form assignments to app users locally
        for app_user_form in app_user_forms:
            app_users[app_user_form.app_user.name].xml_form_ids.append(app_user_form.xml_form_id)
        # Create or update the form assignments on the server
        client.odk_publish.assign_forms(
            app_users=app_users.values(), project_id=form_template.project.project_id
        )


def generate_and_save_app_user_collect_qrcodes(project: Project):
    """Generate and save QR codes for all app users in the project."""
    app_users: QuerySet[AppUser] = project.app_users.all()
    logger.info("Generating QR codes", project=project.name, app_users=len(app_users))
    with ODKPublishClient(base_url=project.central_server.base_url) as client:
        central_app_users = client.odk_publish.get_app_users(
            project_id=project.project_id,
            display_names=[app_user.name for app_user in app_users],
        )
        logger.info("Got central app users", central_app_users=len(central_app_users))
        for app_user in app_users:
            logger.info("Generating QR code", app_user=app_user.name)
            image = create_app_user_qrcode(
                app_user=central_app_users[app_user.name],
                base_url=project.central_server.base_url,
                project_id=project.project_id,
                project_name_prefix=project.name,
            )
            app_user.qr_code.save(
                f"{app_user.name}.png", SimpleUploadedFile("qrcode.png", image.getvalue())
            )
            # app_user.save()
