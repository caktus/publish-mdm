from pathlib import Path
import pytest

from apps.publish_mdm.etl.odk.client import PublishMDMClient

from tests.publish_mdm.factories import CentralServerFactory


@pytest.mark.django_db
class TestNewClient:
    @pytest.fixture
    def central_server(self):
        return CentralServerFactory(base_url="https://central")

    def test_new_client(self, central_server):
        client = PublishMDMClient(central_server=central_server)
        assert client.session.base_url == "https://central/v1/"
        assert client.session.auth.username == central_server.username
        assert client.session.auth.password == central_server.password

    def test_new_client_context_manager(self, central_server):
        with PublishMDMClient(central_server=central_server) as client:
            assert client.session.base_url == "https://central/v1/"
            assert client.session.auth.username == central_server.username
            assert client.session.auth.password == central_server.password

    def test_stub_config_created(self, central_server):
        stub_config_path = Path(f"/tmp/.pyodk_config_{central_server.id}.toml")
        stub_config_path.unlink(missing_ok=True)
        PublishMDMClient(central_server=central_server)
        assert stub_config_path.exists()

    def test_stub_cache_created(self, central_server):
        stub_cache_path = Path(f"/tmp/.pyodk_cache_{central_server.id}.toml")
        stub_cache_path.unlink(missing_ok=True)
        PublishMDMClient(central_server=central_server)
        assert stub_cache_path.exists()
        assert stub_cache_path.read_text() == 'token = ""'

    def test_check_unset_client_project_id(self, central_server):
        assert PublishMDMClient(central_server=central_server).project_id is None

    def test_set_client_project_id(self, central_server):
        client = PublishMDMClient(central_server=central_server, project_id=1)
        assert client.project_id == 1
        assert client.projects.default_project_id == 1
        assert client.forms.default_project_id == 1
        assert client.publish_mdm.project_users.default_project_id == 1
        assert client.publish_mdm.form_assignments.default_project_id == 1

    def test_no_post_retries(self, requests_mock, central_server):
        """Ensures retries are not allowed for POST requests."""
        client = PublishMDMClient(central_server=central_server)
        for adapter in client.session.adapters.values():
            assert "POST" not in adapter.max_retries.allowed_methods


@pytest.mark.django_db
class TestPublishMDMAuthService:
    @pytest.fixture
    def central_server(self):
        return CentralServerFactory(base_url="https://central")

    @pytest.fixture(autouse=True)
    def disable_client_auth(self):
        # Override the auto-used fixture from tests/publish_mdm/conftest.py to
        # enable ODK Central authentication API requests
        return

    def test_token_verification_failure(self, requests_mock, caplog, central_server):
        # Mock token verification failure
        mock_token_verification = requests_mock.get(
            "https://central/v1/users/current",
            status_code=401,
            json={
                "message": "Could not authenticate with the provided credentials.",
                "code": 401.2,
            },
        )
        # Mock getting a new token, done automatically after token verification fails
        mock_get_token = requests_mock.post("https://central/v1/sessions", json={"token": "token"})

        client = PublishMDMClient(central_server=central_server, project_id=1)

        # Do any API request, which automatically should try to verify the currently
        # cached access token
        requests_mock.get("https://central/v1/projects/1/app-users", json=[])
        client.publish_mdm.get_app_users()

        assert mock_token_verification.called_once
        assert mock_get_token.called_once
        # Ensure the 'token verification request failed' message is logged with DEBUG level
        for record in caplog.records:
            if "The token verification request failed" in record.message:
                assert record.levelname == "DEBUG"
                break
        else:
            pytest.fail("No 'token verification request failed' message was logged.")

    def test_token_verification_success(self, requests_mock, caplog, central_server):
        # Mock token verification success
        mock_token_verification = requests_mock.get(
            "https://central/v1/users/current", status_code=200
        )
        # Mock getting a new token, which should not happen if current token is valid
        mock_get_token = requests_mock.post("https://central/v1/sessions", json={"token": "token"})

        client = PublishMDMClient(central_server=central_server, project_id=1)

        # Do any API request, which automatically should try to verify the currently
        # cached access token
        requests_mock.get("https://central/v1/projects/1/app-users", json=[])
        client.publish_mdm.get_app_users()

        assert mock_token_verification.called_once
        assert not mock_get_token.called
