import contextlib
import tempfile
from pathlib import Path
from typing import Callable

import structlog
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import QuerySet
from django.core.files.storage import storages
from pydantic import BaseModel, field_validator
from storages.base import BaseStorage

from apps.users.models import User

from ..models import (
    AppUser,
    CentralServer,
    FormTemplate,
    FormTemplateVersion,
    Project,
)
from .odk.client import ODKPublishClient
from .odk.qrcode import create_app_user_qrcode

logger = structlog.getLogger(__name__)


class PublishTemplateEvent(BaseModel):
    """Model to parse and validate the publish WebSocket message payload."""

    form_template: int
    app_users: list[str]

    @field_validator("app_users", mode="before")
    @classmethod
    def split_comma_separated_app_users(cls, data):
        """Split comma-separated app users into a list."""
        if isinstance(data, str):
            return [user for i in data.split(",") if (user := i.strip())]
        return data


def publish_form_template(event: PublishTemplateEvent, user: User, send_message: Callable):
    """The main function for publishing a form template to ODK Central.

    Steps include:
    * Download the form template from Google Sheets
    * Create the next version of the form template and app user versions
    * Get or create app users in ODK Central
    * Publish each app user version to ODK Central
    """
    send_message(f"New {repr(event)}")
    # Get the form template
    form_template = FormTemplate.objects.select_related().get(id=event.form_template)
    send_message(f"Publishing next version of {repr(form_template)}")
    # Get the next version by querying ODK Central
    client = ODKPublishClient(
        base_url=form_template.project.central_server.base_url,
        project_id=form_template.project.central_id,
    )
    version = client.odk_publish.get_unique_version_by_form_id(
        xml_form_id_base=form_template.form_id_base
    )
    send_message(f"Generated version: {version}")
    # Download the template from Google Sheets
    file = form_template.download_user_google_sheet(
        name=f"{form_template.form_id_base}-{version}.xlsx"
    )
    send_message(f"Downloaded template: {file}")
    with transaction.atomic():
        # Create the next version locally
        template_version = FormTemplateVersion.objects.create(
            form_template=form_template, user=user, file=file, version=version
        )
        # Create a version for each app user locally
        app_users = form_template.get_app_users(names=event.app_users)
        attachments = {i.name: i.file for i in form_template.project.attachments.all()}
        app_user_versions = template_version.create_app_user_versions(
            app_users=app_users, send_message=send_message, attachments=attachments
        )
        # Get or create app users in ODK Central
        central_app_user_assignments = client.odk_publish.get_or_create_app_users(
            display_names=[app_user.name for app_user in app_users]
        )
        send_message(f"Synced user(s): {', '.join(central_app_user_assignments.keys())}")
        # Assign this form to the app users
        for app_user_version in app_user_versions:
            central_app_user_assignments[app_user_version.app_user.name].xml_form_ids.append(
                app_user_version.xml_form_id
            )
        # At this point `attachments` will contain only the attachments detected
        # in the form. Get local absolute paths for them
        with attachment_paths_for_upload(attachments) as attachment_paths:
            # Publish each app user form version to ODK Central
            for app_user_version in app_user_versions:
                form = client.odk_publish.create_or_update_form(
                    xml_form_id=app_user_version.app_user_form_template.xml_form_id,
                    definition=app_user_version.file.read(),
                    attachments=attachment_paths,
                )
                send_message(f"Published form: {form.xmlFormId}")
        # Create or update the form assignments on the server
        for assignment in central_app_user_assignments.values():
            client.odk_publish.assign_app_users_forms(app_users=[assignment])
            send_message(f"Assigned user {assignment.displayName} to {assignment.xml_form_ids[0]}")
        # Update AppUsers with null central_id
        update_app_users_central_id(
            project=form_template.project, app_users=central_app_user_assignments
        )
    send_message(f"Successfully published {version}", complete=True)


@transaction.atomic
def update_app_users_central_id(project: Project, app_users):
    """Update AppUser.central_id for any user related to `project` that has a
    null central_id, using the data in `app_users`. `app_users` should be a dict
    mapping user names to ProjectAppUserAssignment objects, like the dict returned
    by PublishService.get_or_create_app_users().
    """
    for app_user in project.app_users.filter(name__in=app_users, central_id__isnull=True):
        app_user.central_id = app_users[app_user.name].id
        app_user.save()
        logger.info(
            "Updated AppUser.central_id",
            id=app_user.id,
            name=app_user.name,
            central_id=app_user.central_id,
        )


def generate_and_save_app_user_collect_qrcodes(project: Project):
    """Generate and save QR codes for all app users in the project."""
    app_users: QuerySet[AppUser] = project.app_users.all()
    logger.info("Generating QR codes", project=project.name, app_users=len(app_users))
    with ODKPublishClient(
        base_url=project.central_server.base_url, project_id=project.central_id
    ) as client:
        central_app_users = client.odk_publish.get_or_create_app_users(
            display_names=[app_user.name for app_user in app_users],
        )
        logger.info("Got central app users", central_app_users=len(central_app_users))
        for app_user in app_users:
            logger.info("Generating QR code", app_user=app_user.name)
            image, app_user.qr_code_data = create_app_user_qrcode(
                app_user=central_app_users[app_user.name],
                base_url=client.session.base_url,
                project_id=project.central_id,
                project_name_prefix=project.name,
            )
            app_user.qr_code.save(
                f"{app_user.name}.png",
                SimpleUploadedFile("qrcode.png", image.getvalue(), content_type="image/png"),
            )


def sync_central_project(base_url: str, project_id: int) -> Project:
    """Sync a project from ODK Central to the local database."""
    config = ODKPublishClient.get_config(base_url=base_url)
    with ODKPublishClient(base_url=config.base_url, project_id=project_id) as client:
        # CentralServer
        server, created = CentralServer.objects.get_or_create(base_url=base_url)
        logger.debug(
            f"{'Created' if created else 'Retrieved'} CentralServer", base_url=server.base_url
        )
        # Project
        central_project = client.projects.get()
        project, created = Project.objects.get_or_create(
            central_id=central_project.id,
            central_server=server,
            defaults={"name": central_project.name},
        )
        logger.info(
            f"{'Created' if created else 'Retrieved'} Project",
            id=project.id,
            central_id=project.central_id,
            project_name=project.name,
        )
        # AppUser
        central_app_users = client.odk_publish.get_app_users()
        for central_app_user in central_app_users.values():
            if not central_app_user.deletedAt:
                app_user, created = project.app_users.get_or_create(
                    central_id=central_app_user.id,
                    defaults={"name": central_app_user.displayName},
                )
                logger.info(
                    f"{'Created' if created else 'Retrieved'} AppUser",
                    id=app_user.id,
                    central_id=app_user.central_id,
                    app_user_name=app_user.name,
                )
        # FormTemplate
        central_forms = client.odk_publish.get_forms()
        central_form_templates = client.odk_publish.find_form_templates(
            app_users=central_app_users, forms=central_forms
        )
        for form_id_base, app_users in central_form_templates.items():
            form_name = app_users[0].forms[0].name.split("[")[0].strip()
            form_template, created = project.form_templates.get_or_create(
                form_id_base=form_id_base,
                defaults={"title_base": form_name},
            )
            logger.info(
                f"{'Created' if created else 'Retrieved'} FormTemplate",
                id=form_template.id,
                form_id_base=form_template.form_id_base,
                form_title_base=form_template.title_base,
            )
            for app_user in app_users:
                app_user_form, created = form_template.app_user_forms.get_or_create(
                    app_user=project.app_users.get(central_id=app_user.id),
                )
                logger.info(
                    f"{'Created' if created else 'Retrieved'} AppUserFormTemplate",
                    id=app_user_form.id,
                )

    return project


@contextlib.contextmanager
def attachment_paths_for_upload(attachments: dict[str, SimpleUploadedFile]):
    """Get local filesystem paths for the attachments provided. The attachments
    should be the values from the `ProjectAttachment.file` field. If an external
    storage is being used (like S3), the attachments will be downloaded and saved
    in temp files.
    """
    if not isinstance(storages["default"], BaseStorage):
        # Just return the paths if the default storage is a local filesystem
        yield [file.path for file in attachments.values()]
    else:
        with tempfile.TemporaryDirectory() as tmpdirname:
            temp_dir = Path(tmpdirname)
            paths = []
            for name, file in attachments.items():
                path = temp_dir / name
                logger.debug("Temporarily saving attachment for upload", path=path)
                path.write_bytes(file.read())
                paths.append(path)
            yield paths
