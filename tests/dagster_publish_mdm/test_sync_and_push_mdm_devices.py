import dagster as dg
import pytest

from apps.mdm.mdms import get_active_mdm_class
from dagster_publish_mdm.assets.mdm_devices import SyncFleetsConfig, sync_and_push_mdm_devices
from tests.mdm import TestAllMDMs
from tests.mdm.factories import FleetFactory


@pytest.mark.django_db
class TestSyncAndPushMDMDevices(TestAllMDMs):
    """Test suite for syncing MDM fleets and pushing device configurations."""

    def test_sync_fleet_called_for_each_fleet(self, mocker, set_mdm_env_vars, organization):
        """sync_fleet() is called for each fleet in the organization, with push_config=True."""
        mock_sync = mocker.patch.object(get_active_mdm_class(), "sync_fleet")
        fleet1, fleet2 = FleetFactory.create_batch(2, organization=organization)

        sync_and_push_mdm_devices(
            context=dg.build_asset_context(),
            config=SyncFleetsConfig(organization_pk=organization.pk),
        )

        assert mock_sync.call_count == 2
        mock_sync.assert_any_call(fleet1, push_config=True)
        mock_sync.assert_any_call(fleet2, push_config=True)

    def test_no_matching_fleets(self, mocker, set_mdm_env_vars, organization):
        """When the organization has no fleets, sync_fleet() is never called."""
        mock_sync = mocker.patch.object(get_active_mdm_class(), "sync_fleet")
        # Create some fleets in other organizations
        FleetFactory.create_batch(2)

        sync_and_push_mdm_devices(
            context=dg.build_asset_context(),
            config=SyncFleetsConfig(organization_pk=organization.pk),
        )

        mock_sync.assert_not_called()

    def test_no_active_mdm(self, mocker):
        """When the active MDM is not configured, sync_fleet() is never called."""
        mock_sync = mocker.patch.object(get_active_mdm_class(), "sync_fleet")
        fleet = FleetFactory()

        sync_and_push_mdm_devices(
            context=dg.build_asset_context(),
            config=SyncFleetsConfig(organization_pk=fleet.organization.pk),
        )

        mock_sync.assert_not_called()
