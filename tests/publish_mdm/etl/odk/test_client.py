from pathlib import Path
import pytest
from pydantic import ValidationError

from apps.publish_mdm.etl.odk.client import PublishMDMClient


class TestNewClient:
    def test_new_client(self):
        client = PublishMDMClient(base_url="https://central")
        assert client.session.base_url == "https://central/v1/"
        assert client.session.auth.username == "username"
        assert client.session.auth.password == "password"

    def test_new_client_context_manager(self):
        with PublishMDMClient(base_url="https://central") as client:
            assert client.session.base_url == "https://central/v1/"
            assert client.session.auth.username == "username"
            assert client.session.auth.password == "password"

    def test_stub_config_created(self):
        stub_config_path = Path("/tmp/.pyodk_config.toml")
        stub_config_path.unlink(missing_ok=True)
        PublishMDMClient(base_url="https://central")
        assert stub_config_path.exists()

    def test_stub_cache_created(self):
        stub_cache_path = Path("/tmp/.pyodk_cache.toml")
        stub_cache_path.unlink(missing_ok=True)
        PublishMDMClient(base_url="https://central")
        assert stub_cache_path.exists()
        assert stub_cache_path.read_text() == 'token = ""'

    def test_check_unset_client_project_id(self):
        assert PublishMDMClient(base_url="https://central").project_id is None

    def test_set_client_project_id(self):
        client = PublishMDMClient(base_url="https://central", project_id=1)
        assert client.project_id == 1
        assert client.projects.default_project_id == 1
        assert client.forms.default_project_id == 1
        assert client.publish_mdm.project_users.default_project_id == 1
        assert client.publish_mdm.form_assignments.default_project_id == 1

    def test_no_post_retries(self, requests_mock):
        """Ensures retries are not allowed for POST requests."""
        client = PublishMDMClient(base_url="https://central")
        for adapter in client.session.adapters.values():
            assert "POST" not in adapter.max_retries.allowed_methods


class TestPublishMDMAuthService:
    @pytest.fixture(autouse=True)
    def disable_client_auth(self, monkeypatch):
        # Override the auto-used fixture from tests/publish_mdm/conftest.py to
        # enable ODK Central authentication API requests
        monkeypatch.setenv(
            "ODK_CENTRAL_CREDENTIALS",
            "base_url=https://central;username=username;password=password",
        )

    def test_token_verification_failure(self, requests_mock, caplog):
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

        client = PublishMDMClient(base_url="https://central", project_id=1)

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

    def test_token_verification_success(self, requests_mock, caplog):
        # Mock token verification success
        mock_token_verification = requests_mock.get(
            "https://central/v1/users/current", status_code=200
        )
        # Mock getting a new token, which should not happen if current token is valid
        mock_get_token = requests_mock.post("https://central/v1/sessions", json={"token": "token"})

        client = PublishMDMClient(base_url="https://central", project_id=1)

        # Do any API request, which automatically should try to verify the currently
        # cached access token
        requests_mock.get("https://central/v1/projects/1/app-users", json=[])
        client.publish_mdm.get_app_users()

        assert mock_token_verification.called_once
        assert not mock_get_token.called


class TestODKCentralCredentials:
    def test_single_server(self, monkeypatch):
        monkeypatch.setenv(
            "ODK_CENTRAL_CREDENTIALS",
            "base_url=https://myserver.com/;username=user1;password=pass1",
        )
        configs = PublishMDMClient.get_configs()
        assert set(configs.keys()) == {"https://myserver.com"}
        assert configs["https://myserver.com"].username == "user1"
        assert configs["https://myserver.com"].password.get_secret_value() == "pass1"

    def test_multiple_servers(self, monkeypatch):
        monkeypatch.setenv(
            "ODK_CENTRAL_CREDENTIALS",
            "base_url=https://myserver.com;username=user1;password=pass1,base_url=https://otherserver.com;username=user2;password=pass2",
        )
        configs = PublishMDMClient.get_configs()
        assert set(configs.keys()) == {"https://myserver.com", "https://otherserver.com"}
        assert configs["https://myserver.com"].username == "user1"
        assert configs["https://myserver.com"].password.get_secret_value() == "pass1"
        assert configs["https://otherserver.com"].username == "user2"
        assert configs["https://otherserver.com"].password.get_secret_value() == "pass2"

    def test_no_credentials(self, monkeypatch):
        monkeypatch.delenv("ODK_CENTRAL_CREDENTIALS", raising=False)
        assert PublishMDMClient.get_configs() == {}

    def test_invalid_credentials(self, monkeypatch):
        monkeypatch.setenv("ODK_CENTRAL_CREDENTIALS", "invalid")
        assert PublishMDMClient.get_configs() == {}

    def test_missing_full_server_config(self, monkeypatch):
        monkeypatch.setenv("ODK_CENTRAL_CREDENTIALS", "base_url=https://onlyserver.com")
        with pytest.raises(ValidationError):
            PublishMDMClient.get_configs()

    def test_get_config(self, monkeypatch):
        monkeypatch.setenv(
            "ODK_CENTRAL_CREDENTIALS",
            "base_url=https://myserver.com;username=user1;password=pass1",
        )
        config = PublishMDMClient.get_config("https://myserver.com/")
        assert config.username == "user1"
        assert config.password.get_secret_value() == "pass1"

    def test_get_config_missing(self, monkeypatch):
        monkeypatch.setenv(
            "ODK_CENTRAL_CREDENTIALS",
            "base_url=https://myserver.com;username=user1;password=pass1",
        )
        with pytest.raises(KeyError):
            PublishMDMClient.get_config("https://otherserver.com/")
