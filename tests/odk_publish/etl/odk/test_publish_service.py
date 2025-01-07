import pytest

from pyodk.errors import PyODKError

from apps.odk_publish.etl.odk.publish import ProjectAppUserAssignment
from apps.odk_publish.etl.odk.client import ODKPublishClient


@pytest.fixture
def odk_client():
    with ODKPublishClient(base_url="https://central") as client:
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
        app_users = odk_client.odk_publish.get_app_users(project_id=1)
        assert app_users.keys() == {"10000", "20000"}
        app_user = app_users["10000"]
        assert app_user.id == 1
        assert app_user.displayName == "10000"
        assert app_user.token == "token1"

    def test_get_app_users_ignores_no_token(self, requests_mock, odk_client, user_response):
        user_response[0]["token"] = None
        requests_mock.get("https://central/v1/projects/1/app-users", json=[user_response[0]])
        assert odk_client.odk_publish.get_app_users(project_id=1) == {}

    def test_get_app_users_filters_by_display_names(self, requests_mock, odk_client, user_response):
        requests_mock.get("https://central/v1/projects/1/app-users", json=user_response)
        app_users = odk_client.odk_publish.get_app_users(project_id=1, display_names=["10000"])
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
        app_users = odk_client.odk_publish.get_or_create_app_users(
            display_names=["10000", "30000"], project_id=1
        )
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
                createdAt="2025-01-07T14:18:37.300Z",
                updatedAt=None,
                deletedAt=None,
                token="token1",
                form_ids=["myform_10000"],
            ),
        }

    def test_assign_app_users_forms(self, requests_mock, app_users, odk_client):
        requests_mock.post(
            "https://central/v1/projects/1/forms/myform_10000/assignments/2/1",
            json={"success": True},
        )
        odk_client.odk_publish.assign_app_users_forms(app_users=app_users.values(), project_id=1)
        assert requests_mock.call_count == 1

    def test_assign_app_users_forms_already_assigned(self, requests_mock, app_users, odk_client):
        requests_mock.post(
            "https://central/v1/projects/1/forms/myform_10000/assignments/2/1",
            json={"code": "409.3", "success": False},
            status_code=409,
        )
        odk_client.odk_publish.assign_app_users_forms(app_users=app_users.values(), project_id=1)
        assert requests_mock.call_count == 1

    def test_assign_app_users_forms_unexpected_error(self, requests_mock, app_users, odk_client):
        requests_mock.post(
            "https://central/v1/projects/1/forms/myform_10000/assignments/2/1",
            json={"code": "500.1", "success": False},
            status_code=500,
        )
        with pytest.raises(PyODKError):
            odk_client.odk_publish.assign_app_users_forms(
                app_users=app_users.values(), project_id=1
            )
        assert requests_mock.call_count == 1
