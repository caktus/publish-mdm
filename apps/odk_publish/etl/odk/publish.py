from typing import TYPE_CHECKING

import structlog
from pyodk._endpoints import bases
from pyodk._endpoints.form_assignments import FormAssignmentService
from pyodk._endpoints.project_app_users import ProjectAppUser, ProjectAppUserService
from pyodk.errors import PyODKError

from .constants import APP_USER_ROLE_ID

if TYPE_CHECKING:
    from .client import ODKPublishClient


logger = structlog.getLogger(__name__)


class ProjectAppUserAssignment(ProjectAppUser):
    """Extended ProjectAppUser with additional form_ids attribute."""

    form_ids: list[str] = []


class PublishService(bases.Service):
    """ODK Publish helpers for interacting with ODK Central."""

    def __init__(self, client: "ODKPublishClient"):
        self.client = client
        self.project_users = ProjectAppUserService(session=self.client.session)
        self.form_assignments = FormAssignmentService(session=self.client.session)
        logger.info("Initialized ODK Publish service")

    def get_app_users(
        self, project_id: int, display_names: list[str] = None
    ) -> dict[str, ProjectAppUserAssignment]:
        """Return a mapping of display names to ProjectAppUserAssignments for the given project."""
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

    def assign_app_users_forms(
        self, app_users: list[ProjectAppUserAssignment], project_id: int
    ) -> None:
        """Assign forms to app users."""
        for app_user in app_users:
            for form_id in app_user.form_ids:
                try:
                    self.form_assignments.assign(
                        role_id=APP_USER_ROLE_ID,
                        user_id=app_user.id,
                        form_id=form_id,
                        project_id=project_id,
                    )
                    logger.debug(
                        "Assigned form",
                        form_id=form_id,
                        app_user=app_user.displayName,
                        project_id=project_id,
                    )
                except PyODKError as e:
                    if not e.is_central_error(code="409.3"):
                        raise
                    logger.debug(
                        "Form already assigned",
                        form_id=form_id,
                        app_user=app_user.displayName,
                        project_id=project_id,
                    )
