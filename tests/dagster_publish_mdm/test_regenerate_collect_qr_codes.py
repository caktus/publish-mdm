from unittest.mock import call

import dagster as dg
import pytest
import requests
from pyodk.errors import PyODKError

from apps.mdm.mdms import get_active_mdm_class
from dagster_publish_mdm.assets.mdm_devices import (
    RegenerateCollectQRCodesConfig,
    regenerate_collect_qr_codes_and_push_to_devices,
)
from tests.mdm import TestAllMDMs
from tests.mdm.factories import DeviceFactory, FleetFactory
from tests.publish_mdm.factories import AppUserFactory, CollectSettingsFactory, ProjectFactory


@pytest.mark.django_db
class TestRegenerateCollectQRCodesAndPushToDevices(TestAllMDMs):
    """Tests for regenerate_collect_qr_codes_and_push_to_devices."""

    @staticmethod
    def invoke(collect_settings):
        return regenerate_collect_qr_codes_and_push_to_devices(
            context=dg.build_asset_context(),
            config=RegenerateCollectQRCodesConfig(collect_settings_pk=collect_settings.pk),
        )

    @pytest.fixture
    def mock_generate_qr(self, mocker):
        return mocker.patch(
            "dagster_publish_mdm.assets.mdm_devices.generate_and_save_app_user_collect_qrcodes"
        )

    def test_no_linked_projects_returns_early(self, mocker, organization, mock_generate_qr, capsys):
        """When CollectSettings has no linked projects, QR gen and push are both skipped."""
        mock_push = mocker.patch.object(get_active_mdm_class(organization), "push_device_config")
        cs = CollectSettingsFactory(organization=organization)

        self.invoke(cs)

        mock_generate_qr.assert_not_called()
        mock_push.assert_not_called()
        captured = capsys.readouterr()
        assert f"There are no projects using CollectSettings {cs.pk}" in captured.err

    def test_qr_regenerated_for_each_linked_project(
        self, mocker, organization, mock_generate_qr, capsys
    ):
        """generate_and_save_app_user_collect_qrcodes is called once per linked project."""
        mocker.patch.object(get_active_mdm_class(organization), "push_device_config")
        mock_push = mocker.patch.object(get_active_mdm_class(organization), "push_device_config")
        cs = CollectSettingsFactory(organization=organization)
        projects = ProjectFactory.create_batch(2, collect_settings=cs, organization=organization)

        self.invoke(cs)

        assert mock_generate_qr.call_count == 2
        mock_generate_qr.assert_has_calls([call(p) for p in projects], any_order=True)
        # push_device_config not called as the projects have no devices
        mock_push.assert_not_called()
        captured = capsys.readouterr()
        assert "Regenerating QR codes for 2 projects" in captured.err
        for p in projects:
            assert f"Regenerated QR codes for project {p.name!r}" in captured.err
            assert f"There are no devices to push to for project {p.name!r}" in captured.err

    def test_matching_devices_are_pushed(self, mocker, organization, mock_generate_qr, capsys):
        """Devices whose app_user_name matches a project app user get push_device_config called."""
        mock_push = mocker.patch.object(get_active_mdm_class(organization), "push_device_config")
        cs = CollectSettingsFactory(organization=organization)
        project = ProjectFactory(collect_settings=cs, organization=organization)
        app_user = AppUserFactory(project=project, name="match")
        fleet = FleetFactory(organization=organization, project=project)
        device = DeviceFactory(fleet=fleet, app_user_name=app_user.name)
        # push_device_config should not be called for Devices without app_user_name
        # that matches the projects app users
        DeviceFactory(fleet=fleet, app_user_name="")
        DeviceFactory(fleet=fleet, app_user_name="nomatch")

        self.invoke(cs)

        mock_push.assert_called_once_with(device=device)
        captured = capsys.readouterr()
        assert f"Regenerated QR codes for project {project.name!r}" in captured.err
        assert f"Pushed config to device {device.device_id!r}" in captured.err

    @pytest.mark.parametrize("qr_error", [requests.exceptions.RequestException, PyODKError])
    def test_qr_failure_skips_device_push_for_that_project(
        self, mocker, organization, mock_generate_qr, qr_error, capsys
    ):
        """If QR code generation fails, device push is skipped for that project.
        Both RequestException and PyODKError are caught and allow processing to continue.
        """
        mock_push = mocker.patch.object(get_active_mdm_class(organization), "push_device_config")
        cs = CollectSettingsFactory(organization=organization)
        project = ProjectFactory(collect_settings=cs, organization=organization)
        app_user = AppUserFactory(project=project)
        fleet = FleetFactory(organization=organization, project=project)
        DeviceFactory(fleet=fleet, app_user_name=app_user.name)
        mock_generate_qr.side_effect = qr_error("error")

        self.invoke(cs)  # should not raise

        mock_push.assert_not_called()
        captured = capsys.readouterr()
        assert "Regenerating QR codes for 1 projects" in captured.err
        assert f"Failed to regenerate QR codes for project {project.name!r}" in captured.err

    def test_qr_failure_for_one_project_does_not_stop_others(
        self, mocker, organization, mock_generate_qr, capsys
    ):
        """QR code failure for one project does not prevent other projects from being processed."""
        mock_push = mocker.patch.object(get_active_mdm_class(organization), "push_device_config")
        cs = CollectSettingsFactory(organization=organization)
        project_fail = ProjectFactory(collect_settings=cs, organization=organization)
        project_ok = ProjectFactory(collect_settings=cs, organization=organization)
        app_user = AppUserFactory(project=project_ok)
        fleet = FleetFactory(organization=organization, project=project_ok)
        device = DeviceFactory(fleet=fleet, app_user_name=app_user.name)

        def qr_side_effect(project):
            if project == project_fail:
                raise requests.exceptions.RequestException("fail")

        mock_generate_qr.side_effect = qr_side_effect

        self.invoke(cs)

        mock_push.assert_called_once_with(device=device)
        captured = capsys.readouterr()
        assert "Regenerating QR codes for 2 projects" in captured.err
        assert f"Failed to regenerate QR codes for project {project_fail.name!r}" in captured.err
        assert f"Regenerated QR codes for project {project_ok.name!r}" in captured.err
        assert f"Pushed config to device {device.device_id!r}" in captured.err

    def test_no_active_mdm_skips_device_push(
        self, mocker, organization, mock_generate_qr, unconfigure_mdm, capsys
    ):
        """When the active MDM is not configured, QR codes are still generated but push is skipped."""
        mock_push = mocker.patch.object(get_active_mdm_class(organization), "push_device_config")
        cs = CollectSettingsFactory(organization=organization)
        project = ProjectFactory(collect_settings=cs, organization=organization)
        app_user = AppUserFactory(project=project)
        fleet = FleetFactory(organization=organization, project=project)
        DeviceFactory(fleet=fleet, app_user_name=app_user.name)

        self.invoke(cs)

        mock_generate_qr.assert_called_once_with(project)
        mock_push.assert_not_called()
        captured = capsys.readouterr()
        assert "Regenerating QR codes for 1 projects" in captured.err
        assert f"MDM not configured for organization {organization}" in captured.err
        assert f"Regenerated QR codes for project {project.name!r}" in captured.err

    def test_device_push_failure_does_not_stop_other_devices(
        self, mocker, organization, mock_generate_qr, mdm_api_error, capsys
    ):
        """A push failure for one device does not prevent other devices from being pushed."""
        mock_push = mocker.patch.object(get_active_mdm_class(organization), "push_device_config")
        cs = CollectSettingsFactory(organization=organization)
        project = ProjectFactory(collect_settings=cs, organization=organization)
        app_user1 = AppUserFactory(project=project)
        app_user2 = AppUserFactory(project=project)
        fleet = FleetFactory(organization=organization, project=project)
        device1 = DeviceFactory(fleet=fleet, app_user_name=app_user1.name)
        device2 = DeviceFactory(fleet=fleet, app_user_name=app_user2.name)
        mock_push.side_effect = [mdm_api_error, None]

        self.invoke(cs)  # should not raise

        assert mock_push.call_count == 2
        mock_push.assert_any_call(device=device1)
        mock_push.assert_any_call(device=device2)
        captured = capsys.readouterr()
        assert f"Regenerated QR codes for project {project.name!r}" in captured.err
        assert "Failed to push config" in captured.err
        assert "Pushed config to device" in captured.err
