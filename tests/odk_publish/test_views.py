import json
import os
import shutil
from io import StringIO

import pytest
from django.urls import reverse
from django.conf import settings
from django.db.models import Q
from import_export.formats.base_formats import CSV
from import_export.tmp_storages import MediaStorage
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
from apps.odk_publish.forms import AppUserConfirmImportForm, AppUserImportForm
from apps.odk_publish.models import AppUser, FormTemplate


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


class TestImport(ViewTestBase):
    """Test the AppUser import process."""

    @pytest.fixture
    def url(self, project):
        return reverse(
            "odk_publish:app-users-import",
            kwargs={"odk_project_pk": project.pk},
        )

    @pytest.fixture
    def csv_data(self):
        """Valid CSV import data with one new user."""
        return "id,name,central_id,form_templates\n,newuser,,"

    def teardown_class(cls):
        shutil.rmtree(os.path.join(settings.MEDIA_ROOT, "django-import-export"))

    def test_valid_upload(self, client, url, user, csv_data):
        """Ensure the review page is shown after a valid import file is uploaded."""
        data = {"format": 0, "import_file": StringIO(csv_data)}
        response = client.post(url, data=data)
        assert response.status_code == 200
        assert isinstance(response.context["form"], AppUserConfirmImportForm)
        assert (
            "Below is a preview of data to be imported. If you are satisfied "
            "with the results, click 'Confirm import'."
        ) in response.content.decode()
        assert len(response.context["result"].valid_rows()) == 1
        # The user should not be created yet
        assert AppUser.objects.count() == 0
        # The CSV data should be saved in a temp file
        import_format = CSV("utf-8-sig")
        tmp_storage = MediaStorage(
            name=response.context["form"].initial["import_file_name"],
            encoding=import_format.encoding,
            read_mode=import_format.get_read_mode(),
        )
        assert tmp_storage.read().decode(import_format.encoding) == csv_data

    def test_import_confirmed(self, client, url, user, csv_data, project):
        """Ensure confirming the import in the review page updates users."""
        # Save the CSV data in a temp file, as would happen when a valid file is uploaded
        import_format = CSV("utf-8-sig")
        tmp_storage = MediaStorage(
            encoding=import_format.encoding,
            read_mode=import_format.get_read_mode(),
        )
        tmp_storage.save(csv_data)
        # Submit a form for confirming the import
        data = {
            "import_file_name": tmp_storage.name,
            "original_file_name": "test.csv",
            "format": 0,
            "resource": "",
        }
        response = client.post(url, data=data, follow=True)
        # A new user is created and there's a redirect to the user list page
        # with a success message
        assert response.status_code == 200
        assert AppUser.objects.count() == 1
        assert response.redirect_chain == [
            (reverse("odk_publish:app-user-list", args=[project.id]), 302)
        ]
        assert (
            "Import finished successfully, with 1 new and 0 updated app users."
            in response.content.decode()
        )

    def test_invalid_upload(self, client, url, user, csv_data, project):
        """Ensure form validation errors are displayed in case of invalid data in the upload."""
        # Add a row with an invalid central_id
        csv_data += "\n,newuser2,xx,"
        data = {"format": 0, "import_file": StringIO(csv_data)}
        response = client.post(url, data=data)
        response_content = response.content.decode()
        expected_error = "Value must be an integer."
        result = response.context["result"]

        assert response.status_code == 200
        assert isinstance(response.context["form"], AppUserImportForm)
        assert (
            "Please correct these errors in your data where possible, then reupload "
            "it using the form above."
        ) in response_content
        assert len(result.invalid_rows) == 1
        assert result.invalid_rows[0].field_specific_errors["central_id"] == [expected_error]
        assert expected_error in response_content
        # A user should not be created
        assert AppUser.objects.count() == 0


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


class TestAddFormTemplate(ViewTestBase):
    """Test the adding a form template."""

    @pytest.fixture
    def url(self, project):
        return reverse(
            "odk_publish:add-form-template",
            kwargs={"odk_project_pk": project.pk},
        )

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200
        # Ensure the context includes the variables required for the Google Picker JS
        for var in ("google_client_id", "google_api_key", "google_app_id"):
            assert response.context[var] == getattr(settings, var.upper())
        assert response.context["google_scopes"] == " ".join(
            settings.SOCIALACCOUNT_PROVIDERS["google"]["SCOPE"]
        )
        # Ensure the 'Cross-Origin-Opener-Policy' header has the value required
        # for the Google Picker popup to work correctly
        assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin-allow-popups"

    def test_post(self, client, url, user, project):
        data = {
            "title_base": "Test template",
            "form_id_base": "testing",
            "template_url": "https://docs.google.com/spreadsheets/d/1/edit",
            "template_url_user": user.id,
        }
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure a new FormTemplate was created with the expected values
        assert FormTemplate.objects.count() == 1
        form_template_values = FormTemplate.objects.values("project", *data.keys()).get()
        assert form_template_values.pop("project") == project.id
        assert form_template_values == data
        # Ensure the view redirects to the form templates list page
        assert response.redirect_chain == [
            (reverse("odk_publish:form-template-list", args=[project.id]), 302)
        ]
        # Ensure there is a success message
        assert (
            f"Successfully added {form_template_values['title_base']}." in response.content.decode()
        )


class TestEditFormTemplate(ViewTestBase):
    """Test the editing a form template."""

    @pytest.fixture
    def form_template(self, project):
        return FormTemplateFactory(project=project)

    @pytest.fixture
    def url(self, form_template):
        return reverse(
            "odk_publish:edit-form-template",
            kwargs={
                "odk_project_pk": form_template.project_id,
                "form_template_id": form_template.id,
            },
        )

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200
        # Ensure the context includes the variables required for the Google Picker JS
        for var in ("google_client_id", "google_api_key", "google_app_id"):
            assert response.context[var] == getattr(settings, var.upper())
        assert response.context["google_scopes"] == " ".join(
            settings.SOCIALACCOUNT_PROVIDERS["google"]["SCOPE"]
        )
        # Ensure the 'Cross-Origin-Opener-Policy' header has the value required
        # for the Google Picker popup to work correctly
        assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin-allow-popups"

    def test_post(self, client, url, user, form_template):
        data = {
            "title_base": "Test template",
            "form_id_base": "testing",
            "template_url": "https://docs.google.com/spreadsheets/d/1/edit",
            "template_url_user": user.id,
        }
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure the FormTemplate was edited with the expected values
        assert FormTemplate.objects.count() == 1
        form_template_values = FormTemplate.objects.values("id", "project", *data.keys()).get()
        assert form_template_values.pop("id") == form_template.id
        assert form_template_values.pop("project") == form_template.project_id
        assert form_template_values == data
        # Ensure the view redirects to the form templates list page
        assert response.redirect_chain == [
            (reverse("odk_publish:form-template-list", args=[form_template.project_id]), 302)
        ]
        # Ensure there is a success message
        assert (
            f"Successfully edited {form_template_values['title_base']}."
            in response.content.decode()
        )
