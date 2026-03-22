"""
Security regression tests for the MDM app.

VULN-001 (HUNT-002): Unauthenticated firmware snapshot write endpoint
  - When MDM_FIRMWARE_API_KEY is not configured, the endpoint must reject all
    requests (401) rather than silently accepting them.
"""

import json

import pytest
from django.urls import reverse


# ---------------------------------------------------------------------------
# VULN-001: Unauthenticated firmware snapshot endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFirmwareSnapshotAuth:
    """VULN-001: firmware_snapshot_view must not be reachable without a valid API key."""

    @pytest.fixture
    def url(self):
        return reverse("mdm:firmware_snapshot")

    @pytest.fixture
    def valid_payload(self):
        return json.dumps({"deviceIdentifier": "SN-SECURITY-TEST", "version": "9.9"})

    def test_no_key_configured_rejects_unauthenticated_post(
        self, client, url, valid_payload, settings
    ):
        """When MDM_FIRMWARE_API_KEY is empty (the default), the endpoint must return 401.

        Previously the view logged a warning but allowed the write through — any
        unauthenticated caller could create FirmwareSnapshot records.
        """
        settings.MDM_FIRMWARE_API_KEY = ""
        response = client.post(url, data=valid_payload, content_type="application/json")
        assert response.status_code == 401

    def test_valid_api_key_allows_write(self, client, url, valid_payload, settings):
        """A request with the correct Bearer token must still succeed."""
        settings.MDM_FIRMWARE_API_KEY = "supersecret"
        response = client.post(
            url,
            data=valid_payload,
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer supersecret",
        )
        assert response.status_code == 201

    def test_wrong_api_key_rejected(self, client, url, valid_payload, settings):
        """A request with an incorrect Bearer token must be rejected."""
        settings.MDM_FIRMWARE_API_KEY = "supersecret"
        response = client.post(
            url,
            data=valid_payload,
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer wrongkey",
        )
        assert response.status_code == 401
