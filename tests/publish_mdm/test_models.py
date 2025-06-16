import pytest
from django.db.utils import IntegrityError

from django.core.exceptions import ValidationError
from django.db import connection

from .factories import (
    CentralServerFactory,
    TemplateVariableFactory,
    ProjectFactory,
    ProjectTemplateVariableFactory,
    FormTemplateFactory,
    AppUserFormTemplateFactory,
    FormTemplateVersionFactory,
    AppUserFactory,
    AppUserTemplateVariableFactory,
    OrganizationFactory,
)
from apps.infisical.api import InfisicalKMS
from apps.infisical.fields import EncryptedMixin
from apps.publish_mdm.etl import template
from apps.publish_mdm.models import CentralServer
from tests.mdm.factories import PolicyFactory


@pytest.mark.django_db
class TestCentralServer:
    def test_str(self):
        server = CentralServerFactory.build(base_url="https://live.mycentralserver.com/")
        assert str(server) == "live.mycentralserver.com"

    @pytest.mark.parametrize("field", ["username", "password"])
    def test_username_and_password_encryption(self, mocker, field):
        """Test encryption and decryption of username and password fields."""
        # Ensure it's using the custom Encrypted* field
        db_field = CentralServer._meta.get_field(field)
        assert isinstance(db_field, EncryptedMixin)

        plaintext_value = f"plaintext {field}"
        encrypted_value = f"encrypted {field}"

        # Test encryption when saving in the database
        data = {"username": None, "password": None} | {field: plaintext_value}
        mock_encrypt = mocker.patch.object(InfisicalKMS, "encrypt", return_value=encrypted_value)
        server = CentralServerFactory(**data)
        mock_encrypt.assert_called_once()
        mock_encrypt.assert_called_with("centralserver", plaintext_value)

        # Ensure the value stored in the database is the encrypted value
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {field} from {server._meta.db_table} where id = {server.id}")
            assert cursor.fetchone() == (encrypted_value,)

        # Ensure the value is not decrypted when getting it from the database using
        # the default model manager
        mock_decrypt = mocker.patch.object(InfisicalKMS, "decrypt", return_value=plaintext_value)
        server = CentralServer.objects.get(id=server.id)
        mock_decrypt.assert_not_called()
        assert getattr(server, field) == encrypted_value

        # Ensure the value is decrypted when getting it from the database using
        # the custom model manager
        server = CentralServer.decrypted.get(id=server.id)
        mock_decrypt.assert_called_once()
        mock_decrypt.assert_called_with("centralserver", encrypted_value)
        assert getattr(server, field) == plaintext_value

    def test_decrypt_method(self, mocker):
        """Test the CentralServer.decrypt() method."""
        plaintext_value = "plaintext"
        encrypted_value = "encrypted"
        mocker.patch.object(InfisicalKMS, "encrypt", return_value=encrypted_value)
        mock_decrypt = mocker.patch.object(InfisicalKMS, "decrypt", return_value=plaintext_value)
        server = CentralServerFactory(username=plaintext_value, password=plaintext_value)
        server = CentralServer.objects.get(id=server.id)
        assert server.username == encrypted_value
        assert server.password == encrypted_value

        server.decrypt()
        assert server.username == plaintext_value
        assert server.password == plaintext_value
        assert mock_decrypt.call_count == 2

    def test_decrypt_method_unset_fields(self, mocker):
        """Ensure the CentralServer.decrypt() method does not attempt to decrypt
        null or blank values.
        """
        mock_decrypt = mocker.patch.object(InfisicalKMS, "decrypt")
        server = CentralServerFactory(username=None, password="")
        server = CentralServer.objects.get(id=server.id)
        server.decrypt()
        assert server.username is None
        assert server.password == ""
        mock_decrypt.assert_not_called()


class TestTemplateVariable:
    def test_str(self):
        variable = TemplateVariableFactory.build(name="variable_name")
        assert str(variable) == variable.name


class TestProject:
    def test_str(self):
        project = ProjectFactory.build(name="project", central_id=2)
        assert str(project) == "project (2)"


@pytest.mark.django_db
class TestProjectTemplateVariable:
    def test_create_project_template_variable(self):
        """Test that a project template variable can be created successfully."""
        ptv = ProjectTemplateVariableFactory()
        assert ptv.project is not None
        assert ptv.template_variable is not None
        assert isinstance(ptv.value, str)

    def test_unique_constraint(self):
        """Test that a project cannot have duplicate template variables."""
        project = ProjectFactory()
        template_variable = TemplateVariableFactory()

        # Create first instance
        ProjectTemplateVariableFactory(project=project, template_variable=template_variable)

        # Creating another with the same project & template_variable should raise IntegrityError
        with pytest.raises(IntegrityError):
            ProjectTemplateVariableFactory(project=project, template_variable=template_variable)

    def test_str_method(self):
        """Test that the __str__ method returns the expected format."""
        ptv = ProjectTemplateVariableFactory(value="test-value")
        assert str(ptv) == f"test-value ({ptv.id})"


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

    def test_get_any_template_variable(self):
        """get_any_template_variable() returns the correct value or an empty string."""
        app_user = AppUserFactory()
        app_var = AppUserTemplateVariableFactory(app_user=app_user)
        proj_var = ProjectTemplateVariableFactory(project=app_user.project)
        assert app_user.get_any_template_variable(app_var.template_variable.name) == app_var.value
        assert app_user.get_any_template_variable(proj_var.template_variable.name) == proj_var.value
        app_var_override = AppUserTemplateVariableFactory(
            app_user=app_user, template_variable=proj_var.template_variable
        )
        # Clear the cached property to force a new query
        del app_user.all_template_variables_dict
        assert (
            app_user.get_any_template_variable(proj_var.template_variable.name)
            == app_var_override.value
        )
        # Non-existent variable name should return an empty string
        assert app_user.get_any_template_variable("non-existent-variable-name") == ""

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


@pytest.mark.django_db
class TestOrganization:
    def test_create_default_fleet(self, set_tinymdm_env_vars, mocker, settings):
        """Ensures calling create_default_fleet() creates a default Fleet for an
        organization if a default policy exists.
        """
        organization = OrganizationFactory()
        mock_create_group = mocker.patch("apps.publish_mdm.models.create_group")
        mock_add_group_to_policy = mocker.patch("apps.publish_mdm.models.add_group_to_policy")
        mock_get_enrollment_qr_code = mocker.patch("apps.publish_mdm.models.get_enrollment_qr_code")
        mocker.patch("apps.mdm.tasks.pull_devices")

        # No default policy. The default fleet should not be created
        settings.TINYMDM_DEFAULT_POLICY = None
        organization.create_default_fleet()
        assert not organization.fleets.exists()
        mock_create_group.assert_not_called()
        mock_add_group_to_policy.assert_not_called()
        mock_get_enrollment_qr_code.assert_not_called()

        # Create a default policy and call create_default_fleet() again
        default_policy = PolicyFactory(default_policy=True)
        organization.create_default_fleet()
        assert organization.fleets.filter(name="Default", policy=default_policy).exists()
        mock_create_group.assert_called_once()
        mock_add_group_to_policy.assert_called_once()
        mock_get_enrollment_qr_code.assert_called_once()
