import pytest

from apps.mdm.models import Device
from tests.mdm.factories import DeviceFactory


@pytest.mark.django_db
class TestEnsureScreenStreamToken:
    """Tests for Device.ensure_device_token()."""

    def test_generates_token_when_blank(self):
        device = DeviceFactory(device_token="")
        token = device.ensure_device_token()
        assert token
        assert len(token) > 16
        device.refresh_from_db()
        assert device.device_token == token

    def test_idempotent_when_already_set(self):
        device = DeviceFactory(device_token="existing-token-xyz")
        token = device.ensure_device_token()
        assert token == "existing-token-xyz"

    def test_persisted_without_full_save(self):
        """ensure_device_token uses update() not save(), so it shouldn't
        trigger side effects like push_to_mdm."""
        device = DeviceFactory(device_token="")
        device.ensure_device_token()
        device2 = Device.all_objects.get(pk=device.pk)
        assert device2.device_token == device.device_token
