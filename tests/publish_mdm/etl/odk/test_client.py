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

    @pytest.fixture
    def fake_token(self):
        stub_cache_path = Path("/tmp/.pyodk_cache.toml")
        if stub_cache_path.exists():
            old_contents = stub_cache_path.read_text()
            yield "fake token"
            stub_cache_path.write_text(old_contents)
        else:
            yield "fake token"

    def test_stub_cache_created(self, requests_mock, fake_token):
        stub_cache_path = Path("/tmp/.pyodk_cache.toml")
        stub_cache_path.unlink(missing_ok=True)
        requests_mock.post("https://central/v1/sessions", json={"token": fake_token})
        PublishMDMClient(base_url="https://central")
        assert stub_cache_path.exists()
        assert stub_cache_path.read_text() == f'token = "{fake_token}"\n'

    def test_check_unset_client_project_id(self):
        assert PublishMDMClient(base_url="https://central").project_id is None

    def test_set_client_project_id(self):
        client = PublishMDMClient(base_url="https://central", project_id=1)
        assert client.project_id == 1
        assert client.projects.default_project_id == 1
        assert client.forms.default_project_id == 1
        assert client.publish_mdm.project_users.default_project_id == 1
        assert client.publish_mdm.form_assignments.default_project_id == 1


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
