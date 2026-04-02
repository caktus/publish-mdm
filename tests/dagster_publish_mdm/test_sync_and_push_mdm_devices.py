import dagster as dg
import pytest

from apps.mdm.mdms import get_active_mdm_class
from dagster_publish_mdm.assets.mdm_devices import SyncFleetsConfig, sync_and_push_mdm_devices
from tests.mdm import TestAllMDMs
from tests.mdm.factories import FleetFactory


@pytest.mark.django_db
class TestSyncAndPushMDMDevices(TestAllMDMs):
    """Test suite for syncing MDM fleets and pushing device configurations."""

    def test_sync_fleet_called_for_each_fleet(self, mocker, set_mdm_env_vars):
        """sync_fleet() is called once per fleet in fleet_pks, with push_config=True."""
        mock_sync = mocker.patch.object(get_active_mdm_class(), "sync_fleet")
        fleet1 = FleetFactory()
        fleet2 = FleetFactory()

        sync_and_push_mdm_devices(
            context=dg.build_asset_context(),
            config=SyncFleetsConfig(fleet_pks=[fleet1.pk, fleet2.pk]),
        )

        assert mock_sync.call_count == 2
        mock_sync.assert_any_call(fleet1, push_config=True)
        mock_sync.assert_any_call(fleet2, push_config=True)

    def test_only_specified_fleets_are_synced(self, mocker, set_mdm_env_vars):
        """Only the fleets whose PKs appear in fleet_pks are synced; others are ignored."""
        mock_sync = mocker.patch.object(get_active_mdm_class(), "sync_fleet")
        fleet = FleetFactory()
        FleetFactory()  # exists in DB but not listed in fleet_pks

        sync_and_push_mdm_devices(
            context=dg.build_asset_context(),
            config=SyncFleetsConfig(fleet_pks=[fleet.pk]),
        )

        mock_sync.assert_called_once_with(fleet, push_config=True)

    def test_no_matching_fleets(self, mocker, set_mdm_env_vars):
        """When no fleets match the given PKs, sync_fleet() is never called."""
        mock_sync = mocker.patch.object(get_active_mdm_class(), "sync_fleet")

        sync_and_push_mdm_devices(
            context=dg.build_asset_context(),
            config=SyncFleetsConfig(fleet_pks=[999]),
        )

        mock_sync.assert_not_called()

    def test_no_active_mdm(self, mocker):
        """When the active MDM is not configured, sync_fleet() is never called."""
        mock_sync = mocker.patch.object(get_active_mdm_class(), "sync_fleet")
        fleet = FleetFactory()

        sync_and_push_mdm_devices(
            context=dg.build_asset_context(),
            config=SyncFleetsConfig(fleet_pks=[fleet.pk]),
        )

        mock_sync.assert_not_called()
