import pytest

from apps.odk_publish.forms import PublishTemplateForm
from apps.odk_publish.http import HttpRequest
from tests.odk_publish.factories import AppUserFactory, FormTemplateFactory, ProjectFactory


@pytest.mark.django_db
class TestPublishTemplateForm:
    """Test the PublishTemplateForm form validation."""

    @pytest.fixture
    def req(self):
        request = HttpRequest()
        request.odk_project = ProjectFactory()
        return request

    def test_app_users_do_not_exist(self, req: HttpRequest):
        form_template = FormTemplateFactory(project=req.odk_project)
        data = {"app_users": "user1,user2"}
        form = PublishTemplateForm(data=data, request=req, form_template=form_template)
        assert not form.is_valid()
        assert form.errors["app_users"] == ["Invalid App Users: user1, user2"]

    def test_app_users_one_does_not_exist(self, req: HttpRequest):
        form_template = FormTemplateFactory(project=req.odk_project)
        AppUserFactory(project=req.odk_project, name="user1")
        data = {"app_users": "user1,user2"}
        form = PublishTemplateForm(data=data, request=req, form_template=form_template)
        assert not form.is_valid()
        assert form.errors["app_users"] == ["Invalid App Users: user2"]

    def test_app_users(self, req: HttpRequest):
        form_template = FormTemplateFactory(project=req.odk_project)
        AppUserFactory(project=req.odk_project, name="user1")
        AppUserFactory(project=req.odk_project, name="user2")
        data = {"app_users": "user1,user2", "form_template": form_template.id}
        form = PublishTemplateForm(data=data, request=req, form_template=form_template)
        assert form.is_valid(), form.errors
