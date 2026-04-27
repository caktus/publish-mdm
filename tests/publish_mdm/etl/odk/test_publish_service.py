import datetime as dt
from collections.abc import Generator
from pathlib import Path

import pytest
from django.core.serializers.json import DjangoJSONEncoder
from pyodk.errors import PyODKError

from apps.publish_mdm.etl.odk.client import PublishMDMClient
from apps.publish_mdm.etl.odk.publish import Form, FormDraftAttachment, ProjectAppUserAssignment
from tests.publish_mdm.factories import (
    CentralServerFactory,
    FormTemplateFactory,
    FormTemplateVersionFactory,
)


@pytest.fixture
def odk_client() -> Generator[PublishMDMClient, None, None]:
    central_server = CentralServerFactory.build(id=1, base_url="https://central")
    with PublishMDMClient(central_server=central_server, project_id=1) as client:
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

    def test_get_app_users(self, requests_mock, odk_client: PublishMDMClient, user_response):
        requests_mock.get("https://central/v1/projects/1/app-users", json=user_response)
        app_users = odk_client.publish_mdm.get_app_users()
        assert app_users.keys() == {"10000", "20000"}
        app_user = app_users["10000"]
        assert app_user.id == 1
        assert app_user.displayName == "10000"
        assert app_user.token == "token1"

    def test_get_app_users_ignores_no_token(self, requests_mock, odk_client, user_response):
        user_response[0]["token"] = None
        requests_mock.get("https://central/v1/projects/1/app-users", json=[user_response[0]])
        assert odk_client.publish_mdm.get_app_users() == {}

    def test_get_app_users_filters_by_display_names(self, requests_mock, odk_client, user_response):
        requests_mock.get("https://central/v1/projects/1/app-users", json=user_response)
        app_users = odk_client.publish_mdm.get_app_users(display_names=["10000"])
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
        app_users = odk_client.publish_mdm.get_or_create_app_users(display_names=["10000", "30000"])
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

    def test_assign_app_users_forms(self, requests_mock, app_users, odk_client: PublishMDMClient):
        requests_mock.get(
            "https://central/v1/projects/1/forms/myform_10000/assignments/2",
            json=[],
        )
        requests_mock.post(
            "https://central/v1/projects/1/forms/myform_10000/assignments/2/1",
            json={"success": True},
        )
        odk_client.publish_mdm.assign_app_users_forms(app_users=app_users.values())
        assert requests_mock.call_count == 2

    def test_assign_app_users_forms_already_assigned(
        self, requests_mock, app_users, odk_client: PublishMDMClient
    ):
        requests_mock.get(
            "https://central/v1/projects/1/forms/myform_10000/assignments/2",
            json=[
                user.model_dump(exclude=["xml_form_ids", "forms", "projectId"])
                for user in app_users.values()
            ],
            json_encoder=DjangoJSONEncoder,
        )
        odk_client.publish_mdm.assign_app_users_forms(app_users=app_users.values())
        assert requests_mock.call_count == 1

    def test_assign_app_users_forms_unexpected_error(
        self, requests_mock, app_users, odk_client: PublishMDMClient
    ):
        requests_mock.get(
            "https://central/v1/projects/1/forms/myform_10000/assignments/2",
            json=[],
        )
        requests_mock.post(
            "https://central/v1/projects/1/forms/myform_10000/assignments/2/1",
            json={"code": "500.1", "success": False},
            status_code=500,
        )
        with pytest.raises(PyODKError):
            odk_client.publish_mdm.assign_app_users_forms(app_users=app_users.values())
        assert requests_mock.call_count == 2


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

    def test_get_forms(self, requests_mock, odk_client: PublishMDMClient, form_response):
        requests_mock.get("https://central/v1/projects/1/forms", json=form_response)
        forms = odk_client.publish_mdm.get_forms()
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

    def test_create_form(self, mocker, requests_mock, forms, odk_client: PublishMDMClient):
        definition = Path(__file__).parent / "../transform/ODK XLSForm Template.xlsx"
        # Mock the get_forms method to return the existing forms
        mocker.patch.object(odk_client.publish_mdm, "get_forms", return_value=forms)
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
        form = odk_client.publish_mdm.create_or_update_form(
            xml_form_id="newform_10000", definition=definition
        )
        assert requests_mock.call_count == 1
        assert form.xmlFormId == "newform_10000"
        assert form.name == "New Form"

    def test_update_form(self, mocker, requests_mock, forms, odk_client: PublishMDMClient):
        definition = Path(__file__).parent / "../transform/ODK XLSForm Template.xlsx"
        # Mock the get_forms method to return the existing forms
        mocker.patch.object(odk_client.publish_mdm, "get_forms", return_value=forms)
        # First request is to create a draft
        requests_mock.post(
            "https://central/v1/projects/1/forms/myform_10000/draft",
            json={"success": True},
        )
        # Second request is to get the updated form
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
                "publishedAt": "2023-01-30T23:00:35.880Z",
                "name": "My Form",
            },
        )
        form = odk_client.publish_mdm.create_or_update_form(
            xml_form_id="myform_10000", definition=definition
        )
        assert requests_mock.call_count == 2
        assert form.version == "newversion"

    def test_publish_form_draft(self, requests_mock, odk_client: PublishMDMClient):
        requests_mock.post(
            "https://central/v1/projects/1/forms/myform_10000/draft/publish",
            json={"success": True},
        )
        odk_client.publish_mdm.publish_form_draft(xml_form_id="myform_10000")
        assert requests_mock.call_count == 1


class TestPublishServiceDraftAttachments:
    @pytest.fixture
    def attachment_response(self) -> list[dict]:
        return [
            {
                "name": "hospitals.csv",
                "type": "file",
                "exists": True,
                "blobExists": True,
                "datasetExists": False,
                "hash": "abc123",
                "updatedAt": "2024-01-01T00:00:00.000Z",
            },
            {
                "name": "regions.csv",
                "type": "file",
                "exists": False,
                "blobExists": False,
                "datasetExists": False,
                "hash": None,
                "updatedAt": None,
            },
            {
                "name": "patients",
                "type": "file",
                "exists": True,
                "blobExists": True,
                "datasetExists": True,
                "hash": "def456",
                "updatedAt": "2024-01-01T00:00:00.000Z",
            },
        ]

    def test_list_form_attachments(
        self, requests_mock, odk_client: PublishMDMClient, attachment_response
    ):
        requests_mock.get(
            "https://central/v1/projects/1/forms/myform_10000/draft/attachments",
            json=attachment_response,
        )
        attachments = odk_client.publish_mdm.list_form_attachments(xml_form_id="myform_10000")
        assert len(attachments) == 3
        assert attachments[0].name == "hospitals.csv"
        assert attachments[0].exists is True
        assert attachments[0].datasetExists is False
        assert attachments[2].datasetExists is True

    def test_clear_form_attachment(self, requests_mock, odk_client: PublishMDMClient):
        requests_mock.delete(
            "https://central/v1/projects/1/forms/myform_10000/draft/attachments/hospitals.csv",
            json={"success": True},
        )
        odk_client.publish_mdm.clear_form_attachment(
            xml_form_id="myform_10000", attachment_name="hospitals.csv"
        )
        assert requests_mock.call_count == 1


class TestPublishServiceSyncFormAttachments:
    @pytest.fixture
    def draft_attachments(self) -> list[FormDraftAttachment]:
        return [
            FormDraftAttachment(
                name="hospitals.csv",
                type="file",
                exists=True,
                blobExists=True,
                datasetExists=False,
                hash="abc123",
                updatedAt="2024-01-01T00:00:00.000Z",
            ),
            FormDraftAttachment(
                name="regions.csv",
                type="file",
                exists=False,
                blobExists=False,
                datasetExists=False,
                hash=None,
                updatedAt=None,
            ),
            FormDraftAttachment(
                name="patients",
                type="file",
                exists=True,
                blobExists=True,
                datasetExists=True,
                hash="def456",
                updatedAt="2024-01-01T00:00:00.000Z",
            ),
        ]

    def test_sync_uploads_matching_attachment(
        self, requests_mock, odk_client: PublishMDMClient, draft_attachments, tmp_path
    ):
        """Attachments in the map are uploaded; stale/dataset ones are handled correctly."""
        hospitals_path = tmp_path / "hospitals.csv"
        hospitals_path.write_bytes(b"id,name\n1,General")
        mock_upload = requests_mock.post(
            "https://central/v1/projects/1/forms/myform_10000/draft/attachments/hospitals.csv",
            json={"success": True},
        )
        odk_client.publish_mdm.sync_form_attachments(
            xml_form_id="myform_10000",
            attachment_map={"hospitals.csv": hospitals_path},
            draft_attachments=draft_attachments,
        )
        # 1 upload (hospitals.csv); regions.csv not cleared (exists=False);
        # patients skipped (datasetExists=True)
        assert requests_mock.call_count == 1
        assert mock_upload.call_count == 1

    def test_sync_clears_stale_attachment(
        self, requests_mock, odk_client: PublishMDMClient, draft_attachments
    ):
        """Attachments that exist on the server but are not in the map are cleared."""
        mock_delete = requests_mock.delete(
            "https://central/v1/projects/1/forms/myform_10000/draft/attachments/hospitals.csv",
            json={"success": True},
        )
        odk_client.publish_mdm.sync_form_attachments(
            xml_form_id="myform_10000",
            attachment_map={},
            draft_attachments=draft_attachments,
        )
        # 1 delete (hospitals.csv only; regions.csv has exists=False;
        # patients has datasetExists=True)
        assert requests_mock.call_count == 1
        assert mock_delete.call_count == 1

    def test_sync_skips_dataset_attachments(
        self, requests_mock, odk_client: PublishMDMClient, draft_attachments, tmp_path
    ):
        """Dataset-backed attachments are never uploaded or cleared."""
        patients_path = tmp_path / "patients"
        patients_path.write_bytes(b"data")
        odk_client.publish_mdm.sync_form_attachments(
            xml_form_id="myform_10000",
            attachment_map={"patients": patients_path},
            draft_attachments=[
                FormDraftAttachment(
                    name="patients",
                    type="file",
                    exists=True,
                    blobExists=True,
                    datasetExists=True,
                    hash="def456",
                    updatedAt="2024-01-01T00:00:00.000Z",
                )
            ],
        )
        # No upload or delete for the dataset-backed attachment; no API calls at all
        assert requests_mock.call_count == 0


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
        self, forms, mocker, odk_client: PublishMDMClient, version1, version2, expected
    ):
        forms["myform_10000"].version = version1
        forms["myform_20000"].version = version2
        mocker.patch.object(odk_client.publish_mdm, "get_forms", return_value=forms)
        next_version = odk_client.publish_mdm.get_unique_version_by_form_id(
            xml_form_id_base="myform"
        )
        assert next_version == expected

    @pytest.mark.django_db
    def test_get_next_form_version_with_db_check(self, forms, mocker, odk_client: PublishMDMClient):
        """Ensure the get_unique_version_by_form_id method does not return a version
        that exists in the DB if it's called with the form_template arg.
        """
        today = dt.datetime.today().strftime("%Y-%m-%d")
        forms["myform_10000"].version = f"{today}-v1"
        form_template = FormTemplateFactory(form_id_base="myform", project__central_id=1)
        FormTemplateVersionFactory(form_template=form_template, version=f"{today}-v2")
        mocker.patch.object(odk_client.publish_mdm, "get_forms", return_value=forms)
        next_version = odk_client.publish_mdm.get_unique_version_by_form_id(
            xml_form_id_base="myform",
            form_template=form_template,
        )
        assert not form_template.versions.filter(version=next_version).exists()
