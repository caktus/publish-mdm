import pytest
import datetime as dt
from typing import Generator
from pathlib import Path

from django.core.files.temp import NamedTemporaryFile
from pyodk.errors import PyODKError

from apps.odk_publish.etl.odk.publish import ProjectAppUserAssignment, Form
from apps.odk_publish.etl.odk.client import ODKPublishClient


@pytest.fixture
def odk_client() -> Generator[ODKPublishClient, None, None]:
    with ODKPublishClient(base_url="https://central", project_id=1) as client:
        yield client


class TestPublishServiceAppUsers:
    @pytest.fixture
    def user_response(self) -> list[dict]:
        return [
            {
                "projectId": 1,
                "id": 1,
                "type": "field_key",
                "displayName": "10000",
                "createdAt": "2025-01-07T14:18:37.300Z",
                "updatedAt": None,
                "deletedAt": None,
                "token": "token1",
            },
            {
                "projectId": 1,
                "id": 2,
                "type": "field_key",
                "displayName": "20000",
                "createdAt": "2024-07-08T21:43:16.249Z",
                "updatedAt": None,
                "deletedAt": None,
                "token": "token2",
            },
        ]

    def test_get_app_users(self, requests_mock, odk_client: ODKPublishClient, user_response):
        requests_mock.get("https://central/v1/projects/1/app-users", json=user_response)
        app_users = odk_client.odk_publish.get_app_users()
        assert app_users.keys() == {"10000", "20000"}
        app_user = app_users["10000"]
        assert app_user.id == 1
        assert app_user.displayName == "10000"
        assert app_user.token == "token1"

    def test_get_app_users_ignores_no_token(self, requests_mock, odk_client, user_response):
        user_response[0]["token"] = None
        requests_mock.get("https://central/v1/projects/1/app-users", json=[user_response[0]])
        assert odk_client.odk_publish.get_app_users() == {}

    def test_get_app_users_filters_by_display_names(self, requests_mock, odk_client, user_response):
        requests_mock.get("https://central/v1/projects/1/app-users", json=user_response)
        app_users = odk_client.odk_publish.get_app_users(display_names=["10000"])
        assert app_users.keys() == {"10000"}

    def test_get_or_create_app_users(self, requests_mock, odk_client, user_response):
        requests_mock.get("https://central/v1/projects/1/app-users", json=user_response)
        requests_mock.post(
            "https://central/v1/projects/1/app-users",
            json={
                "projectId": 1,
                "id": 3,
                "type": "field_key",
                "displayName": "30000",
                "createdAt": "2024-07-08T21:43:16.249Z",
                "updatedAt": None,
                "deletedAt": None,
                "token": "token3",
            },
        )
        app_users = odk_client.odk_publish.get_or_create_app_users(display_names=["10000", "30000"])
        assert app_users.keys() == {"10000", "30000"}
        assert app_users["10000"].id == 1
        assert app_users["30000"].id == 3


class TestPublishServiceFormAssignments:
    @pytest.fixture
    def app_users(self) -> dict[str, ProjectAppUserAssignment]:
        return {
            "10000": ProjectAppUserAssignment(
                projectId=1,
                id=1,
                type="field_key",
                displayName="10000",
                createdAt=dt.datetime.now(),
                updatedAt=None,
                deletedAt=None,
                token="token1",
                xml_form_ids=["myform_10000"],
            ),
        }

    def test_assign_app_users_forms(self, requests_mock, app_users, odk_client: ODKPublishClient):
        requests_mock.post(
            "https://central/v1/projects/1/forms/myform_10000/assignments/2/1",
            json={"success": True},
        )
        odk_client.odk_publish.assign_app_users_forms(app_users=app_users.values())
        assert requests_mock.call_count == 1

    def test_assign_app_users_forms_already_assigned(
        self, requests_mock, app_users, odk_client: ODKPublishClient
    ):
        requests_mock.post(
            "https://central/v1/projects/1/forms/myform_10000/assignments/2/1",
            json={"code": "409.3", "success": False},
            status_code=409,
        )
        odk_client.odk_publish.assign_app_users_forms(app_users=app_users.values())
        assert requests_mock.call_count == 1

    def test_assign_app_users_forms_unexpected_error(
        self, requests_mock, app_users, odk_client: ODKPublishClient
    ):
        requests_mock.post(
            "https://central/v1/projects/1/forms/myform_10000/assignments/2/1",
            json={"code": "500.1", "success": False},
            status_code=500,
        )
        with pytest.raises(PyODKError):
            odk_client.odk_publish.assign_app_users_forms(app_users=app_users.values())
        assert requests_mock.call_count == 1


class TestPublishServiceForms:
    @pytest.fixture
    def form_response(self) -> list[dict]:
        return [
            {
                "projectId": 1,
                "xmlFormId": "myform_10000",
                "state": "open",
                "enketoId": "enketoId",
                "enketoOnceId": "enketoOnceId",
                "createdAt": "2023-01-30T22:59:08.846Z",
                "updatedAt": "2024-06-28T18:56:32.144Z",
                "keyId": None,
                "version": "",
                "hash": "hash",
                "sha": "sha",
                "sha256": "sha256",
                "draftToken": None,
                "publishedAt": "2023-01-30T23:00:35.380Z",
                "name": "My Form",
            },
            {
                "projectId": 1,
                "xmlFormId": "otherform_10000",
                "state": "open",
                "enketoId": "enketoId",
                "enketoOnceId": "enketoOnceId",
                "createdAt": "2024-04-26T14:46:35.059Z",
                "updatedAt": "2024-06-28T18:56:32.149Z",
                "keyId": None,
                "version": "2025-01-10-v6",
                "hash": "hash",
                "sha": "sha",
                "sha256": "sha256",
                "draftToken": None,
                "publishedAt": "2024-05-28T16:56:44.150Z",
                "name": "My Other From",
            },
        ]

    @pytest.fixture
    def forms(self, form_response):
        return {form["xmlFormId"]: Form(**form) for form in form_response}

    def test_get_forms(self, requests_mock, odk_client: ODKPublishClient, form_response):
        requests_mock.get("https://central/v1/projects/1/forms", json=form_response)
        forms = odk_client.odk_publish.get_forms()
        assert forms.keys() == {"myform_10000", "otherform_10000"}
        form1 = forms["myform_10000"]
        assert form1.projectId == 1
        assert form1.xmlFormId == "myform_10000"
        assert form1.version == ""
        assert form1.name == "My Form"
        form2 = forms["otherform_10000"]
        assert form2.projectId == 1
        assert form2.xmlFormId == "otherform_10000"
        assert form2.version == "2025-01-10-v6"
        assert form2.name == "My Other From"

    @pytest.mark.parametrize("with_attachments", [False, True])
    def test_create_form(
        self, mocker, requests_mock, forms, odk_client: ODKPublishClient, with_attachments: bool
    ):
        definition = Path(__file__).parent / "../transform/ODK XLSForm Template.xlsx"
        # Mock the get_forms method to return the existing forms
        mocker.patch.object(odk_client.odk_publish, "get_forms", return_value=forms)
        # First request is to create a draft
        requests_mock.post(
            "https://central/v1/projects/1/forms?ignoreWarnings=True&publish=False",
            json={
                "projectId": 1,
                "xmlFormId": "newform_10000",
                "state": "open",
                "enketoId": "enketoId",
                "enketoOnceId": "enketoOnceId",
                "createdAt": "2024-04-26T14:46:35.059Z",
                "updatedAt": "2024-06-28T18:56:32.149Z",
                "keyId": None,
                "version": "",
                "hash": "hash",
                "sha": "sha",
                "sha256": "sha256",
                "draftToken": None,
                "publishedAt": None,
                "name": "New Form",
            },
        )
        # Second request is to publish the draft
        requests_mock.post(
            "https://central/v1/projects/1/forms/newform_10000/draft/publish",
            json={"success": True},
        )
        if with_attachments:
            attachment = NamedTemporaryFile()
            basename = Path(attachment.name).name
            # Third request is to upload the attachment
            requests_mock.post(
                f"https://central/v1/projects/1/forms/newform_10000/draft/attachments/{basename}",
                json={"success": True},
            )
            attachments = [attachment.name]
        else:
            attachments = None
        form = odk_client.odk_publish.create_or_update_form(
            xml_form_id="newform_10000", definition=definition, attachments=attachments
        )
        # Two total requests to the ODK Central API if no attachment, 3 otherwise
        assert requests_mock.call_count == 2 + with_attachments
        assert form.xmlFormId == "newform_10000"
        assert form.name == "New Form"

    @pytest.mark.parametrize("with_attachments", [False, True])
    def test_update_form(
        self, mocker, requests_mock, forms, odk_client: ODKPublishClient, with_attachments: bool
    ):
        definition = Path(__file__).parent / "../transform/ODK XLSForm Template.xlsx"
        # Mock the get_forms method to return the existing forms
        mocker.patch.object(odk_client.odk_publish, "get_forms", return_value=forms)
        # First request is to create a draft
        requests_mock.post(
            "https://central/v1/projects/1/forms/myform_10000/draft",
            json={"success": True},
        )
        # Second request is to publish the draft
        requests_mock.post(
            "https://central/v1/projects/1/forms/myform_10000/draft/publish",
            json={"success": True},
        )
        # Third request is to get the updated form
        requests_mock.get(
            "https://central/v1/projects/1/forms/myform_10000",
            json={
                "projectId": 1,
                "xmlFormId": "myform_10000",
                "state": "open",
                "enketoId": "enketoId",
                "enketoOnceId": "enketoOnceId",
                "createdAt": "2023-01-30T22:59:08.846Z",
                "updatedAt": "2024-06-28T18:56:32.144Z",
                "keyId": None,
                "version": "newversion",
                "hash": "hash",
                "sha": "sha",
                "sha256": "sha256",
                "draftToken": None,
                "publishedAt": "2023-01-30T23:00:35.380Z",
                "name": "My Form",
            },
        )
        if with_attachments:
            attachment = NamedTemporaryFile()
            basename = Path(attachment.name).name
            # Fourth request is to upload the attachment
            requests_mock.post(
                f"https://central/v1/projects/1/forms/myform_10000/draft/attachments/{basename}",
                json={"success": True},
            )
            attachments = [attachment.name]
        else:
            attachments = None
        form = odk_client.odk_publish.create_or_update_form(
            xml_form_id="myform_10000", definition=definition, attachments=attachments
        )
        # Three total requests to the ODK Central API if no attachment, 4 otherwise
        assert requests_mock.call_count == 3 + with_attachments
        assert form.version == "newversion"


class TestPublishServiceFormVersions:
    @pytest.fixture
    def forms(self) -> dict[str, Form]:
        return {
            "myform_10000": Form(
                projectId=1,
                xmlFormId="myform_10000",
                version="1",
                hash="hash",
                state="open",
                createdAt=dt.datetime.now(),
                name="My Form [10000]",
                enketoId="enketoId",
                keyId=None,
                updatedAt=dt.datetime.now(),
                publishedAt=dt.datetime.now(),
            ),
            "myform_20000": Form(
                projectId=1,
                xmlFormId="myform_20000",
                version="2",
                hash="hash",
                state="open",
                createdAt=dt.datetime.now(),
                name="My Form [20000]",
                enketoId="enketoId",
                keyId=None,
                updatedAt=dt.datetime.now(),
                publishedAt=dt.datetime.now(),
            ),
        }

    @pytest.mark.parametrize(
        "version1, version2, expected",
        [
            ("", "", f"{dt.date.today()}-v1"),
            ("foo", "bar", f"{dt.date.today()}-v1"),
            ("foo", f"{dt.date.today()}-v1", f"{dt.date.today()}-v2"),
            (f"{dt.date.today()}-v6", f"{dt.date.today()}-v2", f"{dt.date.today()}-v7"),
            (
                f"{dt.date.today() - dt.timedelta(days=1)}-v1",
                f"{dt.date.today() - dt.timedelta(days=1)}-v2",
                f"{dt.date.today()}-v1",
            ),
        ],
    )
    def test_get_next_form_versions(
        self, forms, mocker, odk_client: ODKPublishClient, version1, version2, expected
    ):
        forms["myform_10000"].version = version1
        forms["myform_20000"].version = version2
        mocker.patch.object(odk_client.odk_publish, "get_forms", return_value=forms)
        next_version = odk_client.odk_publish.get_unique_version_by_form_id(
            xml_form_id_base="myform"
        )
        assert next_version == expected
