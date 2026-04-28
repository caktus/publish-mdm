import json

import pytest

from apps.mdm.models import Device
from tests.mdm.factories import DeviceFactory


@pytest.mark.django_db
class TestDeviceFcmTokenView:
    """Tests for the device_fcm_token_view endpoint."""

    url = "/mdm/api/devices/fcm-token/"

    def test_register_fcm_token(self, client):
        device = DeviceFactory(screen_stream_token="tok-abc")
        resp = client.post(
            self.url,
            data=json.dumps(
                {"fcm_token": "new-fcm-token", "screen_stream_token": "tok-abc"}
            ),
            content_type="application/json",
        )
        assert resp.status_code == 204
        device.refresh_from_db()
        assert device.fcm_token == "new-fcm-token"

    def test_updates_existing_token(self, client):
        device = DeviceFactory(screen_stream_token="tok-abc", fcm_token="old-token")
        resp = client.post(
            self.url,
            data=json.dumps(
                {"fcm_token": "updated-token", "screen_stream_token": "tok-abc"}
            ),
            content_type="application/json",
        )
        assert resp.status_code == 204
        device.refresh_from_db()
        assert device.fcm_token == "updated-token"

    def test_unknown_token_returns_404(self, client):
        resp = client.post(
            self.url,
            data=json.dumps(
                {"fcm_token": "tok", "screen_stream_token": "nonexistent"}
            ),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_missing_fcm_token_returns_400(self, client):
        resp = client.post(
            self.url,
            data=json.dumps({"screen_stream_token": "tok-abc"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_missing_screen_stream_token_returns_400(self, client):
        resp = client.post(
            self.url,
            data=json.dumps({"fcm_token": "tok"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_empty_body_returns_400(self, client):
        resp = client.post(self.url, data="", content_type="application/json")
        assert resp.status_code == 400

    def test_invalid_json_returns_400(self, client):
        resp = client.post(self.url, data="not json", content_type="application/json")
        assert resp.status_code == 400

    def test_get_not_allowed(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 405
