import json

import pytest
from django.urls import reverse
from django.db.models import Q
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers.data import JsonLexer

from tests.odk_publish.factories import (
    AppUserFactory,
    AppUserFormTemplateFactory,
    FormTemplateFactory,
    ProjectFactory,
    UserFactory,
)
from apps.odk_publish.etl.odk.constants import DEFAULT_COLLECT_SETTINGS
from apps.odk_publish.etl.odk.publish import ProjectAppUserAssignment


@pytest.mark.django_db
class ViewTestBase:
    @pytest.fixture
    def user(self, client):
        user = UserFactory()
        user.save()
        client.force_login(user=user)
        return user

    @pytest.fixture
    def project(self):
        return ProjectFactory(central_server__base_url="https://central")

    def test_login_required(self, client, url):
        response = client.get(url)
        assert response.status_code == 302

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200


class TestPublishTemplate(ViewTestBase):
    """Test the PublishTemplateForm form validation."""

    @pytest.fixture
    def form_template(self, project):
        return FormTemplateFactory(project=project)

    @pytest.fixture
    def url(self, project, form_template):
        return reverse(
            "odk_publish:form-template-publish",
            kwargs={"odk_project_pk": project.pk, "form_template_id": form_template.pk},
        )

    def test_post(self, client, url, user, project, form_template):
        app_user = AppUserFormTemplateFactory(
            form_template=form_template, app_user__project=project
        ).app_user
        data = {"app_users": app_user.name, "form_template": form_template.id}
        response = client.post(url, data=data)
        assert response.status_code == 200
        assert response.context["form"].is_valid()

    def test_htmx_post(self, client, url, user, project, form_template):
        app_user = AppUserFormTemplateFactory(
            form_template=form_template, app_user__project=project
        ).app_user
        data = {"app_users": app_user.name, "form_template": form_template.id}
        response = client.post(url, data=data, headers={"HX-Request": "true"})
        assert response.status_code == 200
        # Check that the response triggers the WebSocket connection
        assert 'hx-ws="send"' in str(response.content)


class TestAppUserDetail(ViewTestBase):
    @pytest.fixture
    def app_user(self, project):
        return AppUserFactory(project=project, qr_code_data=DEFAULT_COLLECT_SETTINGS)

    @pytest.fixture
    def url(self, app_user):
        return reverse(
            "odk_publish:app-user-detail",
            kwargs={"odk_project_pk": app_user.project.pk, "app_user_pk": app_user.pk},
        )

    def test_get(self, client, url, user, app_user):
        """Ensure the AppUser detail page contains the syntax-highlighed JSON
        for the QR code data and a button to copy the JSON without newlines and
        extra spaces.
        """
        response = client.get(url)
        assert response.status_code == 200

        app_user.refresh_from_db()
        expected_highlight_html = highlight(
            json.dumps(app_user.qr_code_data, indent=4), JsonLexer(), HtmlFormatter(linenos="table")
        )
        response_html = response.content.decode()

        assert response.context["qr_code_data"] == json.dumps(
            app_user.qr_code_data, separators=(",", ":")
        )
        assert response.context["qr_code_highlight_html"] == expected_highlight_html
        assert expected_highlight_html in response_html
        assert "Copy JSON" in response_html


class TestGenerateQRCodes(ViewTestBase):
    @pytest.fixture
    def app_users(self, project):
        return AppUserFactory.create_batch(3, project=project)

    @pytest.fixture
    def url(self, project):
        return reverse(
            "odk_publish:app-users-generate-qr-codes",
            kwargs={"odk_project_pk": project.pk},
        )

    def test_get(self, client, url, user, project, app_users, mocker):
        """Ensure generating QR codes sets both the qr_code and qr_code_data fields
        for the project's users.
        """
        # Initially, qr_code and qr_code_data fields are not set for all app users
        assert project.app_users.count() == 3
        assert (
            project.app_users.filter(Q(qr_code__gt="") | Q(qr_code_data__isnull=False)).count() == 0
        )

        mocker.patch(
            "apps.odk_publish.etl.odk.publish.PublishService.get_app_users",
            return_value={
                app_user.name: ProjectAppUserAssignment(
                    projectId=project.central_id,
                    id=app_user.central_id,
                    type="field_key",
                    displayName="user1",
                    createdAt=app_user.created_at,
                    updatedAt=None,
                    deletedAt=None,
                    token="token1",
                )
                for app_user in app_users
            },
        )
        response = client.get(url, follow=True)
        assert response.status_code == 200
        assert response.redirect_chain == [
            (reverse("odk_publish:app-user-list", args=[project.id]), 302)
        ]
        # All app users should have their qr_code and qr_code_data fields set now
        assert project.app_users.filter(Q(qr_code="") | Q(qr_code_data__isnull=True)).count() == 0


@pytest.mark.django_db
class TestNonExistentProjectID:
    @pytest.fixture
    def user(self, client):
        user = UserFactory()
        user.save()
        client.force_login(user=user)
        return user

    @pytest.mark.parametrize(
        "url_name",
        [
            "app-user-list",
            "app-users-generate-qr-codes",
            "app-users-export",
            "app-users-import",
            "form-template-list",
        ],
    )
    def test_get_returns_404(self, client, user, url_name):
        """Ensure URLs that take a project ID as an argument return a 404 status code
        instead of a 500 for non-existent project IDs.
        """
        url = reverse(f"odk_publish:{url_name}", args=[99])
        response = client.get(url)
        assert response.status_code == 404
