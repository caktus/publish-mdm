import structlog
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import QuerySet

from ..models import AppUser, AppUserFormTemplate, CentralServer, FormTemplate, Project
from .odk.client import ODKPublishClient
from .odk.qrcode import create_app_user_qrcode
from .transform import group_by_common_prefixes

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
    with ODKPublishClient(
        base_url=project.central_server.base_url, project_id=project.project_id
    ) as client:
        central_app_users = client.odk_publish.get_app_users(
            display_names=[app_user.name for app_user in app_users],
        )
        logger.info("Got central app users", central_app_users=len(central_app_users))
        for app_user in app_users:
            logger.info("Generating QR code", app_user=app_user.name)
            image = create_app_user_qrcode(
                app_user=central_app_users[app_user.name],
                base_url=client.session.base_url,
                project_id=project.project_id,
                project_name_prefix=project.name,
            )
            app_user.qr_code.save(
                f"{app_user.name}.png", SimpleUploadedFile("qrcode.png", image.getvalue())
            )


def sync_central_project(base_url: str, project_id: int):
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
            project_id=central_project.id,
            central_server=server,
            defaults={"name": central_project.name},
        )
        logger.info(
            f"{'Created' if created else 'Retrieved'} Project",
            id=project.id,
            project_id=project.project_id,
            project_name=project.name,
        )
        # AppUser
        central_app_users = client.odk_publish.get_app_users()
        for central_app_user in central_app_users.values():
            if not central_app_user.deletedAt:
                app_user, created = project.app_users.get_or_create(
                    app_user_id=central_app_user.id,
                    defaults={"name": central_app_user.displayName},
                )
                logger.info(
                    f"{'Created' if created else 'Retrieved'} AppUser",
                    id=app_user.id,
                    app_user_id=app_user.app_user_id,
                    app_user_name=app_user.name,
                )
        # FormTemplate
        central_forms = client.odk_publish.get_forms()
        possible_template_ids = group_by_common_prefixes(strings=central_forms.keys())
        for central_form in central_forms.values():
            for template_id, form_ids in possible_template_ids.items():
                if central_form.xmlFormId in form_ids:
                    break
            form, created = project.form_templates.get_or_create(
                form_id_base=central_form.xmlFormId,
                defaults={
                    "title_base": central_form.name,
                },
            )
            logger.info(
                f"{'Created' if created else 'Retrieved'} FormTemplate",
                id=form.id,
                form_id_base=form.form_id_base,
                form_title_base=form.title_base,
            )
        for central_form in central_forms.values():
            print(central_form.xmlFormId)
        raise ValueError
    return project
