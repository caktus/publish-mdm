import pytest
from requests.exceptions import HTTPError

from apps.publish_mdm.etl.load import create_project

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
