import pytest
from requests.exceptions import HTTPError

from apps.publish_mdm.etl.load import create_project


class TestCreateProject:
    def test_success(self, requests_mock):
        base_url = "https://central"
        project_name = "Test"
        mock_api_request = requests_mock.post(
            f"{base_url}/v1/projects", json={"id": 99, "name": project_name}
        )
        project_id = create_project(base_url, project_name)
        assert project_id == 99
        assert mock_api_request.last_request.json() == {"name": project_name}

    def test_error(self, requests_mock):
        base_url = "https://central"
        requests_mock.post(f"{base_url}/v1/projects", status_code=500)
        with pytest.raises(HTTPError):
            create_project(base_url, "Test")
