import pytest
from django.urls import reverse

from tests.odk_publish.factories import (
    AppUserFactory,
    FormTemplateFactory,
    ProjectFactory,
    UserFactory,
)


@pytest.mark.django_db
class TestPublishTemplate:
    """Test the PublishTemplateForm form validation."""

    @pytest.fixture
    def user(self, client):
        user = UserFactory()
        user.save()
        client.force_login(user=user)
        return user

    @pytest.fixture
    def project(self):
        return ProjectFactory()

    @pytest.fixture
    def form_template(self, project):
        return FormTemplateFactory(project=project)

    @pytest.fixture
    def url(self, project, form_template):
        return reverse(
            "odk_publish:form-template-publish",
            kwargs={"odk_project_pk": project.pk, "form_template_id": form_template.pk},
        )

    def test_login_required(self, client, url):
        response = client.get(url)
        assert response.status_code == 302

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200

    def test_post(self, client, url, user, project, form_template):
        app_user = AppUserFactory(project=project)
        data = {"app_users": app_user.name, "form_template": form_template.id}
        response = client.post(url, data=data)
        assert response.status_code == 200
        assert response.context["form"].is_valid()

    def test_htmx_post(self, client, url, user, project, form_template):
        app_user = AppUserFactory(project=project)
        data = {"app_users": app_user.name, "form_template": form_template.id}
        response = client.post(url, data=data, headers={"HX-Request": "true"})
        assert response.status_code == 200
        # Check that the response triggers the WebSocket connection
        assert 'hx-ws="send"' in str(response.content)
