from os import PathLike
from typing import TYPE_CHECKING

import structlog
from pyodk._endpoints import bases
from pyodk._endpoints.form_assignments import FormAssignmentService
from pyodk._endpoints.forms import Form
from pyodk._endpoints.project_app_users import ProjectAppUser, ProjectAppUserService
from pyodk.errors import PyODKError

from .constants import APP_USER_ROLE_ID

if TYPE_CHECKING:
    from .client import ODKPublishClient


logger = structlog.getLogger(__name__)


class ProjectAppUserAssignment(ProjectAppUser):
    """Extended ProjectAppUser with additional form_ids attribute."""

    xml_form_ids: list[str] = []


class PublishService(bases.Service):
    """Custom pyODK service for interacting with ODK Central.

    Key features:
    - Service retains a reference to the client for easy access to other services.
    - Instantiates pyODK's ProjectAppUserService and FormAssignmentService for interacting
      with project app users and form assignments.
    """

    def __init__(self, client: "ODKPublishClient"):
        self.client = client
        self.project_users = ProjectAppUserService(session=self.client.session)
        self.form_assignments = FormAssignmentService(session=self.client.session)
        logger.debug("Initialized ODK Publish service")

    def get_app_users(
        self, project_id: int, display_names: list[str] = None
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
        self, display_names: list[str], project_id: int
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

    def create_or_update_form(
        self,
        xml_form_id: str,
        definition: PathLike | bytes,
        attachments: list[PathLike | bytes] | None = None,
        project_id: int | None = None,
    ) -> Form:
        """Return forms for the given form IDs, creating them if they don't exist."""
        central_forms = self.get_forms(project_id=project_id)
        # Updated an existing form if it exists
        if xml_form_id in central_forms:
            self.client.forms.update(
                form_id=xml_form_id,
                definition=definition,
                attachments=attachments,
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
                attachments=attachments,
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

    def assign_app_users_forms(
        self, app_users: list[ProjectAppUserAssignment], project_id: int
    ) -> None:
        """Assign forms to app users."""
        for app_user in app_users:
            for xml_form_id in app_user.form_ids:
                try:
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
                except PyODKError as e:
                    if not e.is_central_error(code="409.3"):
                        raise
                    logger.debug(
                        "Form already assigned",
                        form_id=xml_form_id,
                        app_user=app_user.displayName,
                        project_id=project_id,
                    )
