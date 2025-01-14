from pathlib import Path
import pytest
from pydantic import ValidationError

from apps.odk_publish.etl.odk.client import ODKPublishClient


class TestNewClient:
    def test_new_client(self):
        client = ODKPublishClient(base_url="https://central")
        assert client.session.base_url == "https://central/v1/"
        assert client.session.auth.username == "username"
        assert client.session.auth.password == "password"

    def test_new_client_context_manager(self):
        with ODKPublishClient(base_url="https://central") as client:
            assert client.session.base_url == "https://central/v1/"
            assert client.session.auth.username == "username"
            assert client.session.auth.password == "password"

    def test_stub_config_created(self):
        stub_config_path = Path("/tmp/.pyodk_config.toml")
        stub_config_path.unlink(missing_ok=True)
        ODKPublishClient(base_url="https://central")
        assert stub_config_path.exists()

    def test_check_unset_client_project_id(self):
        assert ODKPublishClient(base_url="https://central").project_id is None

    def test_set_client_project_id(self):
        client = ODKPublishClient(base_url="https://central", project_id=1)
        assert client.project_id == 1
        assert client.projects.default_project_id == 1
        assert client.forms.default_project_id == 1
        assert client.odk_publish.project_users.default_project_id == 1
        assert client.odk_publish.form_assignments.default_project_id == 1


class TestODKCentralCredentials:
    def test_single_server(self, monkeypatch):
        monkeypatch.setenv(
            "ODK_CENTRAL_CREDENTIALS",
            "base_url=https://myserver.com/;username=user1;password=pass1",
        )
        configs = ODKPublishClient.get_configs()
        assert set(configs.keys()) == {"https://myserver.com"}
        assert configs["https://myserver.com"].username == "user1"
        assert configs["https://myserver.com"].password.get_secret_value() == "pass1"

    def test_multiple_servers(self, monkeypatch):
        monkeypatch.setenv(
            "ODK_CENTRAL_CREDENTIALS",
            "base_url=https://myserver.com;username=user1;password=pass1,base_url=https://otherserver.com;username=user2;password=pass2",
        )
        configs = ODKPublishClient.get_configs()
        assert set(configs.keys()) == {"https://myserver.com", "https://otherserver.com"}
        assert configs["https://myserver.com"].username == "user1"
        assert configs["https://myserver.com"].password.get_secret_value() == "pass1"
        assert configs["https://otherserver.com"].username == "user2"
        assert configs["https://otherserver.com"].password.get_secret_value() == "pass2"

    def test_no_credentials(self, monkeypatch):
        monkeypatch.delenv("ODK_CENTRAL_CREDENTIALS", raising=False)
        assert ODKPublishClient.get_configs() == {}

    def test_invalid_credentials(self, monkeypatch):
        monkeypatch.setenv("ODK_CENTRAL_CREDENTIALS", "invalid")
        assert ODKPublishClient.get_configs() == {}

    def test_missing_full_server_config(self, monkeypatch):
        monkeypatch.setenv("ODK_CENTRAL_CREDENTIALS", "base_url=https://onlyserver.com")
        with pytest.raises(ValidationError):
            ODKPublishClient.get_configs()

    def test_get_config(self, monkeypatch):
        monkeypatch.setenv(
            "ODK_CENTRAL_CREDENTIALS",
            "base_url=https://myserver.com;username=user1;password=pass1",
        )
        config = ODKPublishClient.get_config("https://myserver.com/")
        assert config.username == "user1"
        assert config.password.get_secret_value() == "pass1"

    def test_get_config_missing(self, monkeypatch):
        monkeypatch.setenv(
            "ODK_CENTRAL_CREDENTIALS",
            "base_url=https://myserver.com;username=user1;password=pass1",
        )
        with pytest.raises(KeyError):
            ODKPublishClient.get_config("https://otherserver.com/")
