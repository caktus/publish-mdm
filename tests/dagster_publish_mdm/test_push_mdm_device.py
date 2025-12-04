import dagster as dg
import pytest
import requests

from apps.mdm.mdms import get_active_mdm_class
from dagster_publish_mdm.assets.mdm_devices import DeviceConfig, push_mdm_device_config

from tests.mdm import TestAllMDMs, TestTinyMDMOnly
from tests.mdm.factories import DeviceFactory


@pytest.mark.django_db
class TestPushMDMDeviceConfig(TestAllMDMs):
    """Test suite for pushing MDM device configuration."""

    def test_push_mdm_device_config_called(self, mocker, set_mdm_env_vars):
        """Test pushing MDM device configuration."""
        mock_push = mocker.patch.object(get_active_mdm_class(), "push_device_config")
        device = DeviceFactory()
        push_mdm_device_config(
            context=dg.build_asset_context(), config=DeviceConfig(device_pks=[device.pk])
        )
        mock_push.assert_called_once_with(device=device)

    def test_push_mdm_device_config_no_devices(self, mocker, set_mdm_env_vars):
        """Test pushing MDM device configuration with no devices found."""
        mocker.patch.object(get_active_mdm_class(), "push_device_config")
        with pytest.raises(ValueError, match="not found"):
            push_mdm_device_config(
                context=dg.build_asset_context(), config=DeviceConfig(device_pks=[999])
            )

    def test_push_one_fails_not_all(self, mocker, set_mdm_env_vars):
        """Test pushing MDM device configuration with one device failing."""
        mock_push = mocker.patch.object(get_active_mdm_class(), "push_device_config")
        device1 = DeviceFactory()
        device2 = DeviceFactory()
        # Simulate failure for device1
        mock_push.side_effect = [requests.exceptions.RequestException(), None]

        with pytest.raises(ValueError, match="Failed to push configuration for devices"):
            push_mdm_device_config(
                context=dg.build_asset_context(),
                config=DeviceConfig(device_pks=[device1.pk, device2.pk]),
            )

        assert mock_push.call_count == 2
        mock_push.assert_any_call(device=device1)
        # Ensure device2 was also pushed even if device1 failed
        mock_push.assert_any_call(device=device2)


@pytest.mark.django_db
class TestPushTinyMDMDeviceConfigWithError(TestTinyMDMOnly):
    def test_push_fail_logs_error(self, mocker, requests_mock, set_mdm_env_vars, capsys):
        """Test pushing TinyMDM device configuration logs error."""
        device = DeviceFactory(raw_mdm_device={"user_id": "test_user"})
        requests_mock.put(
            "https://www.tinymdm.net/api/v1/users/test_user",
            json={"error": "My error message"},
            status_code=400,
        )
        with pytest.raises(ValueError, match="Failed to push configuration"):
            # This will raise an error because the request fails
            push_mdm_device_config(
                context=dg.build_asset_context(), config=DeviceConfig(device_pks=[device.pk])
            )
        captured = capsys.readouterr()
        assert "Failed to push configuration" in captured.err
        assert "My error message" in captured.err
