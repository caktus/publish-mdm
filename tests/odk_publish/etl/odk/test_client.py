from pathlib import Path

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
