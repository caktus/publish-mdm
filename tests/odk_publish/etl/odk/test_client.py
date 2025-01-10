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

    def test_check_unset_client_project_id(self):
        assert ODKPublishClient(base_url="https://central").project_id is None

    def test_set_client_project_id(self):
        client = ODKPublishClient(base_url="https://central", project_id=1)
        assert client.project_id == 1
        assert client.projects.default_project_id == 1
        assert client.forms.default_project_id == 1
        assert client.odk_publish.project_users.default_project_id == 1
        assert client.odk_publish.form_assignments.default_project_id == 1
