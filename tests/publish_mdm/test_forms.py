import pytest

from apps.publish_mdm.forms import PublishTemplateForm
from apps.publish_mdm.http import HttpRequest
from tests.publish_mdm.factories import (
    FormTemplateFactory,
    ProjectFactory,
    AppUserFormTemplateFactory,
)


@pytest.mark.django_db
class TestPublishTemplateForm:
    """Test the PublishTemplateForm form validation."""

    @pytest.fixture
    def req(self):
        request = HttpRequest()
        request.odk_project = ProjectFactory()
        return request

    def test_no_app_users(self, req: HttpRequest):
        form_template = FormTemplateFactory(project=req.odk_project)
        form = PublishTemplateForm(data={}, request=req, form_template=form_template)
        assert not form.is_valid()
        assert form.cleaned_data["app_users"] == []

    def test_app_users_do_not_exist(self, req: HttpRequest):
        form_template = FormTemplateFactory(project=req.odk_project)
        data = {"app_users": "user1,user2"}
        form = PublishTemplateForm(data=data, request=req, form_template=form_template)
        assert not form.is_valid()
        assert form.errors["app_users"] == ["Invalid App Users: user1, user2"]

    def test_app_users_one_does_not_exist(self, req: HttpRequest):
        form_template = FormTemplateFactory(project=req.odk_project)
        AppUserFormTemplateFactory(
            form_template=form_template, app_user__name="user1", app_user__project=req.odk_project
        )
        data = {"app_users": "user1,user2"}
        form = PublishTemplateForm(data=data, request=req, form_template=form_template)
        assert not form.is_valid()
        assert form.errors["app_users"] == ["Invalid App Users: user2"]

    def test_app_users(self, req: HttpRequest):
        form_template = FormTemplateFactory(project=req.odk_project)
        AppUserFormTemplateFactory(
            form_template=form_template, app_user__name="user1", app_user__project=req.odk_project
        )
        AppUserFormTemplateFactory(
            form_template=form_template, app_user__name="user2", app_user__project=req.odk_project
        )
        data = {"app_users": "user1,user2", "form_template": form_template.id}
        form = PublishTemplateForm(data=data, request=req, form_template=form_template)
        assert form.is_valid(), form.errors

    def test_app_users_with_spaces(self, req: HttpRequest):
        form_template = FormTemplateFactory(project=req.odk_project)
        AppUserFormTemplateFactory(
            form_template=form_template, app_user__name="user1", app_user__project=req.odk_project
        )
        AppUserFormTemplateFactory(
            form_template=form_template, app_user__name="user2", app_user__project=req.odk_project
        )
        data = {"app_users": " user1, user2 ", "form_template": form_template.id}
        form = PublishTemplateForm(data=data, request=req, form_template=form_template)
        assert form.is_valid(), form.errors
