import base64
import json

import pytest
from django.urls import reverse_lazy
from django.utils.timezone import now

from apps.mdm.mdms import AndroidEnterprise
from apps.mdm.models import Device, DeviceSnapshot
from tests.mdm import TestAndroidEnterpriseOnly
from tests.mdm.factories import DeviceFactory, FleetFactory


@pytest.mark.django_db
class TestAmapiNotificationsView(TestAndroidEnterpriseOnly):
    """Tests for the AMAPI Pub/Sub push notification endpoint."""

    TOKEN = "test-pubsub-token-secret"
    URL = reverse_lazy("mdm:amapi_notifications")

    @staticmethod
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

    @pytest.fixture(autouse=True)
    def set_pubsub_token(self, settings):
        """Set ANDROID_ENTERPRISE_PUBSUB_TOKEN for all tests in this class."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = self.TOKEN

    @pytest.fixture(autouse=True)
    def set_enterprise_env(self, set_mdm_env_vars):
        """Ensure ANDROID_ENTERPRISE_ID is set so enterprise_name resolves correctly.
        The notification endpoint ignores all notifications not related to the current
        enterprise.
        """

    def post(self, client, body, token=TOKEN):
        url = self.URL
        if token:
            url = f"{url}?token={token}"
        return client.post(
            url,
            data=json.dumps(body),
            content_type="application/json",
        )

    @pytest.fixture
    def mock_notification_handler(self, mocker):
        return mocker.patch.object(AndroidEnterprise, "handle_device_notification")

    def test_missing_token_setting_rejects_all_requests(
        self, client, settings, mock_notification_handler
    ):
        """When ANDROID_ENTERPRISE_PUBSUB_TOKEN is not set, all requests are rejected."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = None
        body = self.build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body)
        assert response.status_code == 403
        mock_notification_handler.assert_not_called()

    def test_valid_token_accepted(self, client, mock_notification_handler):
        """A request with the correct token is accepted."""
        body = self.build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body, token=self.TOKEN)
        assert response.status_code == 204
        mock_notification_handler.assert_called_once()

    def test_valid_request_with_different_enterprise_name(self, client, mock_notification_handler):
        """A valid enrollment notification is not handled if it's for a different
        enterprise from the currently configured one.
        """
        body = self.build_pubsub_body({"name": "enterprises/different/devices/abc"})
        response = self.post(client, body, token=self.TOKEN)
        assert response.status_code == 204
        mock_notification_handler.assert_not_called()

    def test_valid_request_with_different_mdm(self, client, settings, mock_notification_handler):
        """A valid enrollment notification is not handled if Android Enterprise is
        not the currently configured MDM.
        """
        settings.ACTIVE_MDM = {"name": "TinyMDM", "class": "apps.mdm.mdms.TinyMDM"}
        body = self.build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body, token=self.TOKEN)
        assert response.status_code == 204
        mock_notification_handler.assert_not_called()

    def test_invalid_token_rejected(self, client, mock_notification_handler):
        """A request with an incorrect token is rejected with 403."""
        body = self.build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body, token="wrong")
        assert response.status_code == 403
        mock_notification_handler.assert_not_called()

    def test_missing_token_rejected(self, client, mock_notification_handler):
        """A request without a token is rejected with 403."""
        body = self.build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body, token=None)
        assert response.status_code == 403
        mock_notification_handler.assert_not_called()

    def test_empty_body_returns_400(self, client, mock_notification_handler):
        response = client.post(
            f"{self.URL}?token={self.TOKEN}", data="", content_type="application/json"
        )
        assert response.status_code == 400
        mock_notification_handler.assert_not_called()

    def test_invalid_json_returns_400(self, client, mock_notification_handler):
        response = client.post(
            f"{self.URL}?token={self.TOKEN}", data="not-json", content_type="application/json"
        )
        assert response.status_code == 400
        mock_notification_handler.assert_not_called()

    def test_missing_data_field_returns_204(self, client, mock_notification_handler):
        """A message without a data payload is accepted (acknowledged) silently."""
        body = {
            "message": {
                "attributes": {"notificationType": "ENROLLMENT"},
                "messageId": "1",
            },
            "subscription": "projects/test/subscriptions/sub",
        }
        response = self.post(client, body)
        assert response.status_code == 204
        mock_notification_handler.assert_not_called()

    def test_invalid_base64_data_returns_400(self, client, mock_notification_handler):
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
        mock_notification_handler.assert_not_called()

    def test_unknown_notification_type_returns_204(self, client, mock_notification_handler):
        """An unknown notification type is acknowledged without processing."""
        body = self.build_pubsub_body(
            {"name": "enterprises/test/devices/abc"}, notification_type="COMMAND"
        )
        response = self.post(client, body)
        assert response.status_code == 204
        mock_notification_handler.assert_not_called()

    def test_enrollment_creates_new_device(self, client):
        """An ENROLLMENT notification for a new device creates a Device record."""
        fleet = FleetFactory()
        device_data = {
            "name": "enterprises/test/devices/newdevice1",
            "state": "ACTIVE",
            "enrollmentTokenData": json.dumps({"fleet": fleet.pk}),
            "hardwareInfo": {"serialNumber": "SN-NEW-001", "manufacturer": "Acme"},
        }
        body = self.build_pubsub_body(device_data, "ENROLLMENT")
        response = self.post(client, body)
        assert response.status_code == 204
        device = Device.objects.get(device_id="newdevice1")
        assert device.fleet == fleet
        assert device.serial_number == "SN-NEW-001"
        assert device.name == device_data["name"]

    def test_enrollment_updates_existing_device(self, client):
        """An ENROLLMENT notification for an existing device updates it."""
        fleet = FleetFactory()
        device = DeviceFactory(fleet=fleet, device_id="existingdev1", serial_number="OLD-SN")
        device_data = {
            "name": "enterprises/test/devices/existingdev1",
            "state": "ACTIVE",
            "enrollmentTokenData": json.dumps({"fleet": fleet.pk}),
            "hardwareInfo": {"serialNumber": "NEW-SN", "manufacturer": "Acme"},
        }
        body = self.build_pubsub_body(device_data, "ENROLLMENT")
        response = self.post(client, body)
        assert response.status_code == 204
        device.refresh_from_db()
        assert device.serial_number == "NEW-SN"

    def test_enrollment_without_fleet_data_skips_creation(self, client):
        """An ENROLLMENT notification without fleet info does not create a device."""
        initial_count = Device.objects.count()
        device_data = {
            "name": "enterprises/test/devices/orphandevice",
            "state": "ACTIVE",
            # No enrollmentTokenData
        }
        body = self.build_pubsub_body(device_data, "ENROLLMENT")
        response = self.post(client, body)
        assert response.status_code == 204
        assert Device.objects.count() == initial_count

    def test_status_report_updates_existing_device(self, client):
        """A STATUS_REPORT notification updates the device and creates a snapshot."""
        fleet = FleetFactory()
        device = DeviceFactory(fleet=fleet, device_id="statusdev1", serial_number="OLD-SN")
        policy_sync_time = now()
        device_data = {
            "name": "enterprises/test/devices/statusdev1",
            "state": "ACTIVE",
            "managementMode": "DEVICE_OWNER",
            "lastPolicySyncTime": policy_sync_time.isoformat(),
            "hardwareInfo": {"serialNumber": "STATUS-SN", "manufacturer": "Acme"},
        }
        body = self.build_pubsub_body(device_data, "STATUS_REPORT")
        snapshot_count_before = DeviceSnapshot.objects.count()
        response = self.post(client, body)
        assert response.status_code == 204
        device.refresh_from_db()
        assert device.serial_number == "STATUS-SN"
        assert device.raw_mdm_device == device_data
        assert DeviceSnapshot.objects.count() == snapshot_count_before + 1
        latest_snapshot = DeviceSnapshot.objects.latest("synced_at")
        assert latest_snapshot.last_sync == policy_sync_time

    def test_status_report_for_unknown_device_returns_204(self, client):
        """A STATUS_REPORT for a device not in our DB is acknowledged silently."""
        device_data = {
            "name": "enterprises/test/devices/unknowndev",
            "state": "ACTIVE",
            "managementMode": "DEVICE_OWNER",
            "lastPolicySyncTime": "2024-01-01T12:00:00Z",
            "hardwareInfo": {"serialNumber": "UNK-SN", "manufacturer": "Acme"},
        }
        body = self.build_pubsub_body(device_data, "STATUS_REPORT")
        response = self.post(client, body)
        assert response.status_code == 204

    def test_status_report_pushes_config_on_provisioning_to_active(self, client, mocker):
        """STATUS_REPORT PROVISIONING→ACTIVE calls push_device_config for a device
        with an app_user_name that doesn't yet have a device-specific policy."""
        mock_push = mocker.patch.object(AndroidEnterprise, "push_device_config")
        fleet = FleetFactory()
        device = DeviceFactory(
            fleet=fleet,
            device_id="provdev",
            app_user_name="user1",
            raw_mdm_device={
                "name": "enterprises/test/devices/provdev",
                "state": "PROVISIONING",
                "policyName": "enterprises/test/policies/default",
            },
        )
        device_data = {
            "name": "enterprises/test/devices/provdev",
            "state": "ACTIVE",
            "policyName": "enterprises/test/policies/default",
            "hardwareInfo": {"serialNumber": "PROV-SN"},
        }
        body = self.build_pubsub_body(device_data, "STATUS_REPORT")
        response = self.post(client, body)
        assert response.status_code == 204
        mock_push.assert_called_once_with(device)

    def test_status_report_no_snapshot_without_sufficient_data(self, client):
        """A STATUS_REPORT lacking lastPolicySyncTime does not create a DeviceSnapshot."""
        fleet = FleetFactory()
        DeviceFactory(fleet=fleet, device_id="nosnapdev")
        device_data = {
            "name": "enterprises/test/devices/nosnapdev",
            "state": "ACTIVE",
            "hardwareInfo": {"serialNumber": "NOSNAP-SN"},
        }
        body = self.build_pubsub_body(device_data, "STATUS_REPORT")
        before = DeviceSnapshot.objects.count()
        response = self.post(client, body)
        assert response.status_code == 204
        assert DeviceSnapshot.objects.count() == before
