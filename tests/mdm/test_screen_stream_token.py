import pytest

from apps.mdm.models import Device
from tests.mdm.factories import DeviceFactory


@pytest.mark.django_db
class TestEnsureScreenStreamToken:
    """Tests for Device.ensure_screen_stream_token()."""

    def test_generates_token_when_blank(self):
        device = DeviceFactory(screen_stream_token="")
        token = device.ensure_screen_stream_token()
        assert token
        assert len(token) > 16
        device.refresh_from_db()
        assert device.screen_stream_token == token

    def test_idempotent_when_already_set(self):
        device = DeviceFactory(screen_stream_token="existing-token-xyz")
        token = device.ensure_screen_stream_token()
        assert token == "existing-token-xyz"

    def test_persisted_without_full_save(self):
        """ensure_screen_stream_token uses update() not save(), so it shouldn't
        trigger side effects like push_to_mdm."""
        device = DeviceFactory(screen_stream_token="")
        device.ensure_screen_stream_token()
        device2 = Device.all_objects.get(pk=device.pk)
        assert device2.screen_stream_token == device.screen_stream_token
