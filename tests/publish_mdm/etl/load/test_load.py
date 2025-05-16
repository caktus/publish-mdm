import pytest
from requests.exceptions import HTTPError

from apps.publish_mdm.etl.load import create_project, sync_central_project
from apps.publish_mdm.models import AppUserFormTemplate

from tests.publish_mdm.factories import CentralServerFactory


@pytest.mark.django_db
class TestCreateProject:
    def test_success(self, requests_mock):
        central_server = CentralServerFactory(base_url="https://central")
        project_name = "Test"
        mock_api_request = requests_mock.post(
            f"{central_server.base_url}/v1/projects", json={"id": 99, "name": project_name}
        )
        project_id = create_project(central_server, project_name)
        assert project_id == 99
        assert mock_api_request.last_request.json() == {"name": project_name}

    def test_error(self, requests_mock):
        central_server = CentralServerFactory(base_url="https://central")
        requests_mock.post(f"{central_server.base_url}/v1/projects", status_code=500)
        with pytest.raises(HTTPError):
            create_project(central_server, "Test")


@pytest.mark.django_db
class TestProjectSync:
    """Test the sync_central_project() function."""

    def test_sync(self, requests_mock):
        server = CentralServerFactory()
        # Mock the ODK Central API request for getting a project
        project_json = {
            "id": 1,
            "name": "Default Project",
            "description": "Description",
            "createdAt": "2025-04-18T23:19:14.802Z",
        }
        requests_mock.get(f"{server.base_url}/v1/projects/1", json=project_json)
        # Mock the ODK Central API request for getting app users
        users_json = [
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
        requests_mock.get(f"{server.base_url}/v1/projects/1/app-users", json=users_json)
        # Mock the ODK Central API request for getting forms
        forms_json = [
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
                "name": "My Other Form [10000]",
            },
        ]
        requests_mock.get(f"{server.base_url}/v1/projects/1/forms", json=forms_json)

        sync_central_project(server=server, project_id=1)

        # Ensure the database has the expected data
        # Project
        project = server.projects.get()
        assert (project.central_id, project.name, project.organization_id) == (
            project_json["id"],
            project_json["name"],
            server.organization_id,
        )
        # AppUsers
        assert project.app_users.count() == 2
        assert set(project.app_users.values_list("central_id", "name")) == {
            (user["id"], user["displayName"]) for user in users_json
        }
        # FormTemplates
        assert project.form_templates.count() == 2
        assert set(project.form_templates.values_list("form_id_base", "title_base")) == {
            (form["xmlFormId"].rsplit("_", 1)[0], form["name"].split("[")[0].strip())
            for form in forms_json
        }
        # AppUserFormTemplates
        assert (
            AppUserFormTemplate.objects.filter(app_user__central_id=users_json[0]["id"]).count()
            == 2
        )
        assert (
            AppUserFormTemplate.objects.filter(app_user__central_id=users_json[1]["id"]).count()
            == 0
        )
