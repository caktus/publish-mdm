import base64
import json

import pytest

from apps.mdm.models import Device, DeviceSnapshot
from tests.mdm import TestAndroidEnterpriseOnly
from tests.mdm.factories import DeviceFactory, FleetFactory


def build_pubsub_body(device_data: dict, notification_type: str = "ENROLLMENT") -> dict:
    """Build a minimal Pub/Sub push notification body."""
    encoded = base64.b64encode(json.dumps(device_data).encode()).decode()
    return {
        "message": {
            "attributes": {"notificationType": notification_type},
            "data": encoded,
            "messageId": "1234567890",
            "publishTime": "2024-01-01T00:00:00Z",
        },
        "subscription": "projects/test/subscriptions/amapi-sub",
    }


@pytest.mark.django_db
class TestAmapiNotificationsView(TestAndroidEnterpriseOnly):
    """Tests for the AMAPI Pub/Sub push notification endpoint."""

    url = "/mdm/api/amapi/notifications/"

    def post(self, client, body, token=None):
        url = self.url
        if token:
            url = f"{url}?token={token}"
        return client.post(
            url,
            data=json.dumps(body),
            content_type="application/json",
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def test_no_token_required_when_env_var_not_set(self, client, monkeypatch):
        """When AMAPI_NOTIF_SECRET_TOKEN is not set, all requests are accepted."""
        monkeypatch.delenv("AMAPI_NOTIF_SECRET_TOKEN", raising=False)
        body = build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body)
        assert response.status_code == 204

    def test_valid_token_accepted(self, client, monkeypatch):
        """A request with the correct token is accepted."""
        monkeypatch.setenv("AMAPI_NOTIF_SECRET_TOKEN", "secret123")
        body = build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body, token="secret123")
        assert response.status_code == 204

    def test_invalid_token_rejected(self, client, monkeypatch):
        """A request with an incorrect token is rejected with 403."""
        monkeypatch.setenv("AMAPI_NOTIF_SECRET_TOKEN", "secret123")
        body = build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body, token="wrong")
        assert response.status_code == 403

    def test_missing_token_rejected(self, client, monkeypatch):
        """A request without a token is rejected with 403 when the env var is set."""
        monkeypatch.setenv("AMAPI_NOTIF_SECRET_TOKEN", "secret123")
        body = build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body)
        assert response.status_code == 403

    # ------------------------------------------------------------------
    # Payload validation
    # ------------------------------------------------------------------

    def test_empty_body_returns_400(self, client, monkeypatch):
        monkeypatch.delenv("AMAPI_NOTIF_SECRET_TOKEN", raising=False)
        response = client.post(self.url, data="", content_type="application/json")
        assert response.status_code == 400

    def test_invalid_json_returns_400(self, client, monkeypatch):
        monkeypatch.delenv("AMAPI_NOTIF_SECRET_TOKEN", raising=False)
        response = client.post(self.url, data="not-json", content_type="application/json")
        assert response.status_code == 400

    def test_missing_data_field_returns_204(self, client, monkeypatch):
        """A message without a data payload is accepted (acknowledged) silently."""
        monkeypatch.delenv("AMAPI_NOTIF_SECRET_TOKEN", raising=False)
        body = {
            "message": {
                "attributes": {"notificationType": "ENROLLMENT"},
                "messageId": "1",
            },
            "subscription": "projects/test/subscriptions/sub",
        }
        response = self.post(client, body)
        assert response.status_code == 204

    def test_invalid_base64_data_returns_400(self, client, monkeypatch):
        monkeypatch.delenv("AMAPI_NOTIF_SECRET_TOKEN", raising=False)
        body = {
            "message": {
                "attributes": {"notificationType": "ENROLLMENT"},
                "data": "!!!not-valid-base64!!!",
                "messageId": "1",
            },
            "subscription": "projects/test/subscriptions/sub",
        }
        response = self.post(client, body)
        assert response.status_code == 400

    def test_unknown_notification_type_returns_204(self, client, monkeypatch):
        """An unknown notification type is acknowledged without processing."""
        monkeypatch.delenv("AMAPI_NOTIF_SECRET_TOKEN", raising=False)
        body = build_pubsub_body(
            {"name": "enterprises/test/devices/abc"}, notification_type="COMMAND"
        )
        response = self.post(client, body)
        assert response.status_code == 204

    # ------------------------------------------------------------------
    # ENROLLMENT notification handling
    # ------------------------------------------------------------------

    def test_enrollment_creates_new_device(self, client, monkeypatch, settings):
        """An ENROLLMENT notification for a new device creates a Device record."""
        monkeypatch.delenv("AMAPI_NOTIF_SECRET_TOKEN", raising=False)
        settings.ACTIVE_MDM = {
            "name": "Android Enterprise",
            "class": "apps.mdm.mdms.AndroidEnterprise",
        }
        fleet = FleetFactory()
        device_data = {
            "name": "enterprises/test/devices/newdevice1",
            "state": "ACTIVE",
            "enrollmentTokenData": json.dumps({"fleet": fleet.pk}),
            "hardwareInfo": {"serialNumber": "SN-NEW-001", "manufacturer": "Acme"},
        }
        body = build_pubsub_body(device_data, "ENROLLMENT")
        response = self.post(client, body)
        assert response.status_code == 204
        device = Device.objects.get(device_id="newdevice1")
        assert device.fleet == fleet
        assert device.serial_number == "SN-NEW-001"
        assert device.name == device_data["name"]

    def test_enrollment_updates_existing_device(self, client, monkeypatch, settings):
        """An ENROLLMENT notification for an existing device updates it."""
        monkeypatch.delenv("AMAPI_NOTIF_SECRET_TOKEN", raising=False)
        settings.ACTIVE_MDM = {
            "name": "Android Enterprise",
            "class": "apps.mdm.mdms.AndroidEnterprise",
        }
        fleet = FleetFactory()
        device = DeviceFactory(fleet=fleet, device_id="existingdev1", serial_number="OLD-SN")
        device_data = {
            "name": "enterprises/test/devices/existingdev1",
            "state": "ACTIVE",
            "enrollmentTokenData": json.dumps({"fleet": fleet.pk}),
            "hardwareInfo": {"serialNumber": "NEW-SN", "manufacturer": "Acme"},
        }
        body = build_pubsub_body(device_data, "ENROLLMENT")
        response = self.post(client, body)
        assert response.status_code == 204
        device.refresh_from_db()
        assert device.serial_number == "NEW-SN"

    def test_enrollment_without_fleet_data_skips_creation(self, client, monkeypatch, settings):
        """An ENROLLMENT notification without fleet info does not create a device."""
        monkeypatch.delenv("AMAPI_NOTIF_SECRET_TOKEN", raising=False)
        settings.ACTIVE_MDM = {
            "name": "Android Enterprise",
            "class": "apps.mdm.mdms.AndroidEnterprise",
        }
        initial_count = Device.objects.count()
        device_data = {
            "name": "enterprises/test/devices/orphandevice",
            "state": "ACTIVE",
            # No enrollmentTokenData
        }
        body = build_pubsub_body(device_data, "ENROLLMENT")
        response = self.post(client, body)
        assert response.status_code == 204
        assert Device.objects.count() == initial_count

    # ------------------------------------------------------------------
    # STATUS_REPORT notification handling
    # ------------------------------------------------------------------

    def test_status_report_updates_existing_device(self, client, monkeypatch, settings):
        """A STATUS_REPORT notification updates the device metadata."""
        monkeypatch.delenv("AMAPI_NOTIF_SECRET_TOKEN", raising=False)
        settings.ACTIVE_MDM = {
            "name": "Android Enterprise",
            "class": "apps.mdm.mdms.AndroidEnterprise",
        }

        fleet = FleetFactory()
        device = DeviceFactory(fleet=fleet, device_id="statusdev1", serial_number="OLD-SN")
        device_data = {
            "name": "enterprises/test/devices/statusdev1",
            "state": "ACTIVE",
            "managementMode": "DEVICE_OWNER",
            "lastPolicySyncTime": "2024-01-01T12:00:00Z",
            "hardwareInfo": {"serialNumber": "STATUS-SN", "manufacturer": "Acme"},
        }
        body = build_pubsub_body(device_data, "STATUS_REPORT")
        response = self.post(client, body)
        assert response.status_code == 204
        device.refresh_from_db()
        assert device.serial_number == "STATUS-SN"
        assert device.raw_mdm_device == device_data

    def test_status_report_creates_snapshot(self, client, monkeypatch, settings):
        """A STATUS_REPORT with sufficient data creates a DeviceSnapshot."""
        monkeypatch.delenv("AMAPI_NOTIF_SECRET_TOKEN", raising=False)
        settings.ACTIVE_MDM = {
            "name": "Android Enterprise",
            "class": "apps.mdm.mdms.AndroidEnterprise",
        }
        fleet = FleetFactory()
        DeviceFactory(fleet=fleet, device_id="snapdev1")
        device_data = {
            "name": "enterprises/test/devices/snapdev1",
            "state": "ACTIVE",
            "managementMode": "DEVICE_OWNER",
            "lastPolicySyncTime": "2024-01-01T12:00:00Z",
            "hardwareInfo": {"serialNumber": "SNAP-SN", "manufacturer": "Acme"},
        }
        body = build_pubsub_body(device_data, "STATUS_REPORT")
        snapshot_count_before = DeviceSnapshot.objects.count()
        response = self.post(client, body)
        assert response.status_code == 204
        assert DeviceSnapshot.objects.count() == snapshot_count_before + 1

    def test_status_report_for_unknown_device_returns_204(self, client, monkeypatch, settings):
        """A STATUS_REPORT for a device not in our DB is acknowledged silently."""
        monkeypatch.delenv("AMAPI_NOTIF_SECRET_TOKEN", raising=False)
        settings.ACTIVE_MDM = {
            "name": "Android Enterprise",
            "class": "apps.mdm.mdms.AndroidEnterprise",
        }
        device_data = {
            "name": "enterprises/test/devices/unknowndev",
            "state": "ACTIVE",
            "managementMode": "DEVICE_OWNER",
            "lastPolicySyncTime": "2024-01-01T12:00:00Z",
            "hardwareInfo": {"serialNumber": "UNK-SN", "manufacturer": "Acme"},
        }
        body = build_pubsub_body(device_data, "STATUS_REPORT")
        response = self.post(client, body)
        assert response.status_code == 204
