import dagster as dg
import pytest
import requests


from dagster_publish_mdm.assets.tinymdm_devices import DeviceConfig, push_tinymdm_device_config

from tests.mdm.factories import DeviceFactory


@pytest.mark.django_db
class TestPushTinyMDMDeviceConfig:
    """Test suite for pushing TinyMDM device configuration."""

    @pytest.fixture(autouse=True)
    def session(self, mocker):
        """Set up the TinyMDM session for tests."""
        mocker.patch(
            "dagster_publish_mdm.assets.tinymdm_devices.get_tinymdm_session", return_value="session"
        )
        return "session"

    def test_push_tinymdm_device_config_called(self, mocker, session):
        """Test pushing TinyMDM device configuration."""
        mock_push = mocker.patch("dagster_publish_mdm.assets.tinymdm_devices.push_device_config")
        device = DeviceFactory()
        push_tinymdm_device_config(
            context=dg.build_asset_context(), config=DeviceConfig(device_pks=[device.pk])
        )
        mock_push.assert_called_once_with(session=session, device=device)

    def test_push_tinymdm_device_config_no_devices(self, mocker, session):
        """Test pushing TinyMDM device configuration with no devices found."""
        mocker.patch("apps.mdm.tasks.push_device_config")
        with pytest.raises(ValueError, match="not found"):
            push_tinymdm_device_config(
                context=dg.build_asset_context(), config=DeviceConfig(device_pks=[999])
            )

    def test_push_one_fails_not_all(self, mocker, session):
        """Test pushing TinyMDM device configuration with one device failing."""
        mock_push = mocker.patch("dagster_publish_mdm.assets.tinymdm_devices.push_device_config")
        device1 = DeviceFactory()
        device2 = DeviceFactory()
        # Simulate failure for device1
        mock_push.side_effect = [requests.exceptions.RequestException(), None]

        with pytest.raises(ValueError, match="Failed to push configuration for devices"):
            push_tinymdm_device_config(
                context=dg.build_asset_context(),
                config=DeviceConfig(device_pks=[device1.pk, device2.pk]),
            )

        assert mock_push.call_count == 2
        mock_push.assert_any_call(session=session, device=device1)
        # Ensure device2 was also pushed even if device1 failed
        mock_push.assert_any_call(session=session, device=device2)


@pytest.mark.django_db
class TestPushTinyMDMDeviceConfigWithError:
    def test_push_fail_logs_error(self, mocker, requests_mock, set_tinymdm_env_vars, capsys):
        """Test pushing TinyMDM device configuration logs error."""
        device = DeviceFactory(raw_mdm_device={"user_id": "test_user"})
        requests_mock.put(
            "https://www.tinymdm.net/api/v1/users/test_user",
            json={"error": "My error message"},
            status_code=400,
        )
        with pytest.raises(ValueError, match="Failed to push configuration"):
            # This will raise an error because the request fails
            push_tinymdm_device_config(
                context=dg.build_asset_context(), config=DeviceConfig(device_pks=[device.pk])
            )
        captured = capsys.readouterr()
        assert "Failed to push configuration" in captured.err
        assert "My error message" in captured.err
