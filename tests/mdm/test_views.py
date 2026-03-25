import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestFirmwareSnapshotView:
    """Regression tests for firmware_snapshot_view with mandatory API key auth (VULN-002)."""

    API_KEY = "test-firmware-key"

    @pytest.fixture(autouse=True)
    def set_api_key(self, settings):
        settings.MDM_FIRMWARE_API_KEY = self.API_KEY

    @pytest.fixture
    def url(self):
        return reverse("mdm:firmware_snapshot")

    @pytest.fixture
    def auth_headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.API_KEY}"}

    def test_empty_body_returns_400(self, client, url, auth_headers):
        response = client.post(url, data="", content_type="application/json", **auth_headers)
        assert response.status_code == 400

    def test_invalid_json_returns_400(self, client, url, auth_headers):
        response = client.post(
            url, data="not-json", content_type="application/json", **auth_headers
        )
        assert response.status_code == 400

    def test_invalid_form_data_returns_400(self, client, url, auth_headers):
        response = client.post(url, data="{}", content_type="application/json", **auth_headers)
        assert response.status_code == 400

    @pytest.mark.django_db
    def test_valid_data_saves_and_returns_201(self, client, url, auth_headers):
        import json as json_module

        data = json_module.dumps({"deviceIdentifier": "SN-VIEW-TEST", "version": "1.0"})
        response = client.post(url, data=data, content_type="application/json", **auth_headers)
        assert response.status_code == 201
