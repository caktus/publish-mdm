import pytest

from django.core.exceptions import ValidationError

from .factories import (
    CentralServerFactory,
    TemplateVariableFactory,
    ProjectFactory,
    FormTemplateFactory,
    AppUserFormTemplateFactory,
    FormTemplateVersionFactory,
    AppUserFactory,
    AppUserTemplateVariableFactory,
)
from apps.odk_publish.etl import template


class TestCentralServer:
    def test_str(self):
        server = CentralServerFactory.build(base_url="https://live.mycentralserver.com/")
        assert str(server) == "live.mycentralserver.com"


class TestTemplateVariable:
    def test_str(self):
        variable = TemplateVariableFactory.build(name="variable_name")
        assert str(variable) == variable.name


class TestProject:
    def test_str(self):
        project = ProjectFactory.build(name="project", central_id=2)
        assert str(project) == "project (2)"


class TestFormTemplate:
    def test_str(self):
        template = FormTemplateFactory.build(form_id_base="staff_registration", id=2)
        assert str(template) == "staff_registration (2)"

    @pytest.mark.django_db
    def test_get_app_users_no_app_users(self):
        template = FormTemplateFactory.create()
        assert list(template.get_app_users()) == []

    @pytest.mark.django_db
    def test_get_app_users(self):
        template = FormTemplateFactory.create()
        app_user = AppUserFormTemplateFactory.create(form_template=template).app_user
        # other user
        AppUserFormTemplateFactory.create()
        assert list(template.get_app_users()) == [app_user]

    @pytest.mark.django_db
    def test_get_app_users_names(self):
        template = FormTemplateFactory.create()
        app_user = AppUserFormTemplateFactory.create(form_template=template).app_user
        AppUserFormTemplateFactory.create(form_template=template)
        assert template.get_app_users().count() == 2
        assert list(template.get_app_users(names=[app_user.name])) == [app_user]


class TestAppUserFormTemplate:
    def test_xml_form_id(self):
        template = AppUserFormTemplateFactory.build(
            app_user__name="app_user_name", form_template__form_id_base="staff_registration"
        )
        assert template.xml_form_id == "staff_registration_app_user_name"
        assert str(template) == "staff_registration_app_user_name"


class TestFormTemplateVersion:
    def test_str(self):
        version = FormTemplateVersionFactory.build(version="v1")
        assert str(version) == version.file.name


@pytest.mark.django_db
class TestAppUser:
    @pytest.fixture
    def project(self):
        return ProjectFactory()

    def test_get_template_variables(self):
        """Ensures the AppUser.get_template_variables method returns the correct
        template.TemplateVariable objects.
        """
        app_user = AppUserFactory()
        # 2 variables without any transform
        variables = TemplateVariableFactory.create_batch(2)
        # 2 variables with the SHA256_DIGEST transform
        variables += TemplateVariableFactory.create_batch(
            2, transform=template.VariableTransform.SHA256_DIGEST.value
        )
        expected = []

        for variable in variables:
            user_variable = AppUserTemplateVariableFactory(
                template_variable=variable,
                app_user=app_user,
            )
            expected.append(
                template.TemplateVariable(
                    name=variable.name,
                    value=user_variable.value,
                    transform=variable.transform or None,
                )
            )

        assert app_user.get_template_variables() == expected

    @pytest.mark.parametrize(
        "name",
        [
            "11030",
            "01234",
            "abc",
            "ABCD",
            "a000",
            "a:b",
            "aaa:bbb",
            "123:a456",
            "12:_",
            "12:a-a",
            "a-a-a-a",
            "b_b_b",
            "a-a-a:b-b-b",
            "__",
            "--",
            "_1234",
            "abcd_",
            "-1234",
            "1234-",
            ":abc",
            ":a123",
        ],
    )
    def test_valid_names(self, name, project):
        app_user = AppUserFactory.build(name=name, project=project)
        app_user.full_clean()

    @pytest.mark.parametrize(
        "name",
        [
            "its invalid",
            "it's",
            ":",
            "123:",
            ":123",
            "a:b:c",
            "a:123",
            "a b c",
            "ab.cd",
            "abc,def",
            ".*$!",
        ],
    )
    def test_invalid_names(self, name, project):
        app_user = AppUserFactory.build(name=name, project=project)
        with pytest.raises(
            ValidationError,
            match="Name can only contain alphanumeric characters, underscores, hyphens, and not more than one colon.",
        ):
            app_user.full_clean()
