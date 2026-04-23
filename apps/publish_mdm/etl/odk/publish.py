import datetime as dt
from collections import defaultdict
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from pydantic import Field
from pyodk._endpoints import bases
from pyodk._endpoints.form_assignments import FormAssignmentService
from pyodk._endpoints.form_draft_attachments import FormDraftAttachmentService
from pyodk._endpoints.form_drafts import FormDraftService
from pyodk._endpoints.forms import Form, FormService
from pyodk._endpoints.project_app_users import ProjectAppUser, ProjectAppUserService
from pyodk.errors import PyODKError

from .constants import APP_USER_ROLE_ID

if TYPE_CHECKING:
    from .client import PublishMDMClient


logger = structlog.getLogger(__name__)


class FormDraftAttachment(bases.Model):
    """Represents an attachment expected by a form draft.
    https://docs.getodk.org/central-api-form-management/#listing-expected-draft-form-attachments
    """

    name: str
    type: str  # image | audio | video | file
    exists: bool  # True if blobExists or datasetExists
    datasetExists: bool  # File is linked to an entity list / dataset
    blobExists: bool  # Server has the file content
    hash: str | None = None  # MD5 hash of attachment content
    updatedAt: dt.datetime | None = None


class PublishMDMFormService(FormService):
    """FormService subclass that overrides the create() and update() methods to
    create/update form drafts without auto-publishing, so callers can clean up
    stale attachments before publishing the draft.
    """

    def create(
        self,
        definition: PathLike | str | bytes,
        attachments=None,
        ignore_warnings: bool | None = True,
        form_id: str | None = None,
        project_id: int | None = None,
    ) -> Form:
        """Copy of FormService.create() but creates a form draft without publishing it."""
        fd = FormDraftService(session=self.session, **self._default_kw())
        pid, _, headers, params, form_def = fd._prep_form_post(
            definition=definition,
            ignore_warnings=ignore_warnings,
            form_id=form_id,
            project_id=project_id,
        )
        params["publish"] = False
        response = self.session.response_or_error(
            method="POST",
            url=self.session.urlformat(self.urls.forms, project_id=pid),
            logger=logger,
            headers=headers,
            params=params,
            data=form_def,
        )
        form = Form(**response.json())
        fp_ids = {"form_id": form.xmlFormId, "project_id": project_id}
        if attachments is not None:
            fda = FormDraftAttachmentService(session=self.session, **self._default_kw())
            for attach in attachments:
                if not fda.upload(file_path=attach, **fp_ids):
                    raise PyODKError("Form create (attachment upload) failed.")
        return form

    def update(
        self,
        form_id: str,
        project_id: int | None = None,
        definition: PathLike | str | bytes | None = None,
        attachments=None,
        version_updater=None,
    ) -> None:
        """Copy of FormService.update() but updates a form draft without publishing it."""
        if definition is None and attachments is None:
            raise PyODKError("Must specify a form definition and/or attachments.")
        if definition is not None and version_updater is not None:
            raise PyODKError("Must not specify both a definition and version_updater.")
        fp_ids = {"form_id": form_id, "project_id": project_id}
        fd = FormDraftService(session=self.session, **self._default_kw())
        if not fd.create(definition=definition, **fp_ids):
            raise PyODKError("Form update (form draft create) failed.")
        if attachments is not None:
            fda = FormDraftAttachmentService(session=self.session, **self._default_kw())
            for attach in attachments:
                if not fda.upload(file_path=attach, **fp_ids):
                    raise PyODKError("Form update (attachment upload) failed.")


class ProjectAppUserAssignment(ProjectAppUser):
    """Extended ProjectAppUser with additional form_ids attribute."""

    forms: list[Form] = Field(default_factory=list)
    xml_form_ids: list[str] = Field(default_factory=list)


class PublishService(bases.Service):
    """Custom pyODK service for interacting with ODK Central.

    Key features:
    - Service retains a reference to the client for easy access to other services.
    - Defaults to using the client's project ID if not provided, since most operations
      construct a new client.
    - Instantiates pyODK's ProjectAppUserService and FormAssignmentService for interacting
      with project app users and form assignments.
    """

    def __init__(self, client: "PublishMDMClient"):
        self.client = client
        self.project_users = ProjectAppUserService(
            session=self.client.session, default_project_id=self.client.project_id
        )
        self.form_assignments = FormAssignmentService(
            session=self.client.session, default_project_id=self.client.project_id
        )

    def get_app_users(
        self, project_id: int | None = None, display_names: list[str] | None = None
    ) -> dict[str, ProjectAppUserAssignment]:
        """Return a mapping of display names to ProjectAppUserAssignments for
        the given project, filtered by display names if provided.
        """
        app_users = {
            user.displayName: ProjectAppUserAssignment(**dict(user))
            for user in self.project_users.list(project_id=project_id)
            if user.token is not None
        }
        # Filter by display names if provided
        if display_names:
            app_users = {name: user for name, user in app_users.items() if name in display_names}
        return app_users

    def get_or_create_app_users(
        self, display_names: list[str], project_id: int | None = None
    ) -> dict[str, ProjectAppUserAssignment]:
        """Return users for the given display names, creating them if they don't exist."""
        central_users = self.get_app_users(project_id=project_id)
        # Extract existing users
        app_users = {name: user for name in display_names if (user := central_users.get(name))}
        # Create users that don't exist
        to_create_users = {name for name in display_names if name not in central_users}
        for user in to_create_users:
            created_user = self.project_users.create(display_name=user, project_id=project_id)
            logger.info(
                "Created app user", app_user=created_user.displayName, project_id=project_id
            )
            # Add created user to the dictionary
            app_users[created_user.displayName] = ProjectAppUserAssignment(**dict(created_user))
        logger.debug("Retrieved app users", users=list(app_users.keys()), project_id=project_id)
        return app_users

    def get_forms(self, project_id: int | None = None) -> dict[str, Form]:
        """Return a mapping of form IDs to Form objects for the given project."""
        forms = self.client.forms.list(project_id=project_id)
        return {form.xmlFormId: form for form in forms}

    def find_form_templates(
        self, app_users: dict[str, ProjectAppUserAssignment], forms: dict[str, Form]
    ) -> dict[str, list[ProjectAppUserAssignment]]:
        """Return form templates for the given app users and forms."""

        form_templates = defaultdict(list)
        for form in forms.values():
            try:
                xml_form_id_base, maybe_app_user = form.xmlFormId.rsplit("_", 1)
            except ValueError:
                continue
            if app_user := app_users.get(maybe_app_user):
                user = app_user.model_copy(deep=True)
                user.forms.append(form)
                form_templates[xml_form_id_base].append(user)
        logger.info("Found form templates", form_templates=list(form_templates.keys()))
        return form_templates

    def get_unique_version_by_form_id(
        self, xml_form_id_base: str, project_id: int | None = None, form_template=None
    ):
        """
        Generates a new, unique version for the form whose xmlFormId starts with
        the given xml_form_id_base.
        """
        today = dt.datetime.today().strftime("%Y-%m-%d")
        central_forms = self.get_forms(project_id=project_id)
        versions = {
            int(form.version.split("v")[1])
            for form in central_forms.values()
            if form.xmlFormId.startswith(xml_form_id_base) and form.version.startswith(today)
        }
        if form_template:
            # Also check the versions currently in the database for this form template
            versions |= {
                int(version.split("v")[1])
                for version in form_template.versions.filter(version__startswith=today).values_list(
                    "version", flat=True
                )
            }
        new_version = max(versions) + 1 if versions else 1
        full_version = f"{today}-v{new_version}"
        logger.debug(
            "Generated new form version",
            xml_form_id_base=xml_form_id_base,
            version=full_version,
        )
        return full_version

    def create_or_update_form(
        self,
        xml_form_id: str,
        definition: PathLike | bytes,
        project_id: int | None = None,
    ) -> Form:
        """Return forms for the given form IDs, creating them if they don't exist."""
        central_forms = self.get_forms(project_id=project_id)
        # Updated an existing form if it exists
        if xml_form_id in central_forms:
            self.client.forms.update(
                form_id=xml_form_id,
                definition=definition,
                project_id=project_id,
            )
            # Retrieve updated form to get the version
            form = self.client.forms.get(form_id=xml_form_id, project_id=project_id)
            logger.info(
                "Updated form",
                project_id=form.projectId,
                xml_form_id=form.xmlFormId,
                version=form.version,
                name=form.name,
            )
        else:
            # Create form if it doesn't exist
            form = self.client.forms.create(
                form_id=xml_form_id,
                definition=definition,
                project_id=project_id,
            )
            logger.info(
                "Created form",
                project_id=form.projectId,
                xml_form_id=form.xmlFormId,
                version=form.version,
                name=form.name,
            )
        return form

    def sync_form_attachments(
        self,
        xml_form_id: str,
        attachment_map: dict[str, Path],
        draft_attachments: list[FormDraftAttachment],
        project_id: int | None = None,
    ) -> None:
        """Upload expected attachments and clear stale ones from the current form draft.

        For each attachment in draft_attachments where datasetExists=False:
        - If the attachment name is in attachment_map, upload it using the canonical name.
        - If the attachment exists on the server (exists=True) but is not in
          attachment_map, clear it.

        draft_attachments should be the result of list_form_attachments() for this form,
        passed in by the caller to avoid a redundant API call.
        """
        project_id = project_id or self.client.project_id
        fda = FormDraftAttachmentService(session=self.client.session, default_project_id=project_id)
        fp_ids = {"form_id": xml_form_id, "project_id": project_id}
        for attachment in draft_attachments:
            if attachment.datasetExists:
                continue
            if attachment.name in attachment_map:
                logger.info(
                    "Uploading form attachment",
                    xml_form_id=xml_form_id,
                    attachment_name=attachment.name,
                    project_id=project_id,
                )
                if not fda.upload(
                    file_path=attachment_map[attachment.name], file_name=attachment.name, **fp_ids
                ):
                    raise PyODKError(f"Form attachment upload failed for {attachment.name}.")
            else:
                logger.warning(
                    "Expected form attachment not found in project attachments",
                    xml_form_id=xml_form_id,
                    attachment_name=attachment.name,
                    project_id=project_id,
                )
                if attachment.exists:
                    logger.info(
                        "Clearing stale form attachment",
                        xml_form_id=xml_form_id,
                        attachment_name=attachment.name,
                        project_id=project_id,
                    )
                    self.clear_form_attachment(
                        xml_form_id=xml_form_id,
                        attachment_name=attachment.name,
                        project_id=project_id,
                    )

    def publish_form_draft(
        self,
        xml_form_id: str,
        project_id: int | None = None,
    ) -> None:
        """Publish the current draft for the given form.
        https://docs.getodk.org/central-api-form-management/#publishing-a-draft-form
        """
        project_id = project_id or self.client.project_id
        fd = FormDraftService(
            session=self.client.session,
            default_project_id=project_id,
        )
        if not fd.publish(form_id=xml_form_id, project_id=project_id):
            raise PyODKError("Form draft publish failed.")
        logger.info(
            "Published form draft",
            xml_form_id=xml_form_id,
            project_id=project_id,
        )

    def list_form_attachments(
        self,
        xml_form_id: str,
        project_id: int | None = None,
    ) -> list[FormDraftAttachment]:
        """List the expected attachments for the current form draft.
        https://docs.getodk.org/central-api-form-management/#listing-expected-draft-form-attachments
        """
        project_id = project_id or self.client.project_id
        response = self.client.get(f"projects/{project_id}/forms/{xml_form_id}/draft/attachments")
        response.raise_for_status()
        return [FormDraftAttachment(**item) for item in response.json()]

    def clear_form_attachment(
        self,
        xml_form_id: str,
        attachment_name: str,
        project_id: int | None = None,
    ) -> None:
        """Clear a single attachment from the current form draft.
        https://docs.getodk.org/central-api-form-management/#clearing-a-draft-form-attachment
        """
        project_id = project_id or self.client.project_id
        encoded_name = self.client.session.urlquote(attachment_name)
        response = self.client.delete(
            f"projects/{project_id}/forms/{xml_form_id}/draft/attachments/{encoded_name}"
        )
        response.raise_for_status()
        logger.info(
            "Cleared form attachment",
            xml_form_id=xml_form_id,
            attachment_name=attachment_name,
            project_id=project_id,
        )

    def get_app_users_assigned_to_form(self, project_id, form_id):
        """Get a set with the IDs of all app users that have been assigned to a form.
        https://docs.getodk.org/central-api-form-management/#listing-all-actors-assigned-some-form-role
        """
        logger.info(
            "Getting app users assigned to form",
            form_id=form_id,
            project_id=project_id,
        )
        response = self.client.get(
            f"projects/{project_id}/forms/{form_id}/assignments/{APP_USER_ROLE_ID}"
        )
        logger.info(
            "Got app users assigned to form",
            form_id=form_id,
            project_id=project_id,
            response_status_code=response.status_code,
            response_content=response.content,
        )
        if response.status_code == 200:
            return {i["id"] for i in response.json()}
        return set()

    def assign_app_users_forms(
        self, app_users: list[ProjectAppUserAssignment], project_id: int | None = None
    ) -> None:
        """Assign forms to app users."""
        for app_user in app_users:
            for xml_form_id in app_user.xml_form_ids:
                if app_user.id in self.get_app_users_assigned_to_form(
                    project_id or self.client.project_id, xml_form_id
                ):
                    logger.debug(
                        "Form already assigned",
                        form_id=xml_form_id,
                        app_user=app_user.displayName,
                        project_id=project_id,
                    )
                else:
                    self.form_assignments.assign(
                        role_id=APP_USER_ROLE_ID,
                        user_id=app_user.id,
                        form_id=xml_form_id,
                        project_id=project_id,
                    )
                    logger.debug(
                        "Assigned form",
                        form_id=xml_form_id,
                        app_user=app_user.displayName,
                        project_id=project_id,
                    )
