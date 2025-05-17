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

    @pytest.fixture
    def fake_token(self, central_server):
        stub_cache_path = Path(f"/tmp/.pyodk_cache_{central_server.id}.toml")
        if stub_cache_path.exists():
            old_contents = stub_cache_path.read_text()
            yield "fake token"
            stub_cache_path.write_text(old_contents)
        else:
            yield "fake token"

    def test_stub_cache_created(self, requests_mock, fake_token, central_server):
        stub_cache_path = Path(f"/tmp/.pyodk_cache_{central_server.id}.toml")
        stub_cache_path.unlink(missing_ok=True)
        requests_mock.post("https://central/v1/sessions", json={"token": fake_token})
        PublishMDMClient(central_server=central_server)
        assert stub_cache_path.exists()
        assert stub_cache_path.read_text() == f'token = "{fake_token}"\n'

    def test_check_unset_client_project_id(self, central_server):
        assert PublishMDMClient(central_server=central_server).project_id is None

    def test_set_client_project_id(self, central_server):
        client = PublishMDMClient(central_server=central_server, project_id=1)
        assert client.project_id == 1
        assert client.projects.default_project_id == 1
        assert client.forms.default_project_id == 1
        assert client.publish_mdm.project_users.default_project_id == 1
        assert client.publish_mdm.form_assignments.default_project_id == 1
