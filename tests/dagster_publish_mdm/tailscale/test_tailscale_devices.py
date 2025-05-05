import dagster as dg
import pytest
import datetime as dt

from dagster_publish_mdm.assets.tailscale import tailscale_devices as assets
from dagster_publish_mdm.resources.tailscale import TailscaleResource

from apps.tailscale.models import DeviceSnapshot
from tests.tailscale.factories import DeviceSnapshotFactory


@pytest.fixture
def devices() -> dict:
    return {
        "devices": [
            {
                "addresses": ["100.100.1.1"],
                "authorized": True,
                "blocksIncomingConnections": False,
                "clientVersion": "1.76.6-t1edcf9d46-gd0a6cd8b2",
                "created": "2024-10-15T13:58:11Z",
                "expires": "2025-04-13T13:58:11Z",
                "hostname": "ip-172-31-45-72",
                "id": "1111",
                "isExternal": False,
                "keyExpiryDisabled": False,
                "lastSeen": "2024-12-13T16:18:48Z",
                "machineKey": "mkey:key",
                "name": "name.tailnet.ts.net",
                "nodeId": "nodeid",
                "nodeKey": "nodekey:key",
                "os": "linux",
                "tags": ["tag:server"],
                "tailnetLockError": "",
                "tailnetLockKey": "nlpub:key",
                "updateAvailable": True,
                "user": "myuser@github",
            }
        ],
        "tailnet": "tailnet",
    }


def test_tailscale_device_snapshot(requests_mock, devices):
    """Test asset accesses the Tailscale API and returns the devices JSON."""
    tailscale = TailscaleResource(client_id="key", client_secret="secret", tailnet="tailnet")
    requests_mock.post(
        "https://api.tailscale.com/api/v2/oauth/token",
        json={"access_token": "dummy", "expires_in": 3600, "token_type": "Bearer"},
    )
    requests_mock.get(
        f"https://api.tailscale.com/api/v2/tailnet/{tailscale.tailnet}/devices",
        json=devices,
    )
    result = assets.tailscale_device_snapshot(context=dg.build_asset_context(), tailscale=tailscale)
    assert result == devices


@pytest.mark.django_db
def test_tailscale_append_device_snapshot_table(devices):
    """Test asset creates DeviceSnapshot objects from the devices JSON."""
    assets.tailscale_append_device_snapshot_table(
        context=dg.build_asset_context(), tailscale_device_snapshot=devices
    )
    assert DeviceSnapshot.objects.count() == 1
    data = devices["devices"][0]
    device = DeviceSnapshot.objects.first()
    assert device.addresses == data["addresses"]
    assert device.client_version == data["clientVersion"]
    assert device.created == dt.datetime.fromisoformat(data["created"])
    assert device.expires == dt.datetime.fromisoformat(data["expires"])
    assert device.hostname == data["hostname"]
    assert device.last_seen == dt.datetime.fromisoformat(data["lastSeen"])
    assert device.name == data["name"]
    assert device.node_id == data["nodeId"]
    assert device.os == data["os"]
    assert device.tags == data["tags"]
    assert device.update_available == data["updateAvailable"]
    assert device.user == data["user"]
    assert device.tailnet == devices["tailnet"]
    assert device.raw_data == data
    assert device.synced_at is not None


@pytest.mark.django_db
def test_device_no_expiration(devices):
    """Test asset handles devices with no expiration date."""
    devices["devices"][0]["expires"] = "0001-01-01T00:00:00Z"
    assets.tailscale_append_device_snapshot_table(
        context=dg.build_asset_context(), tailscale_device_snapshot=devices
    )
    device = DeviceSnapshot.objects.first()
    assert device.expires is None


@pytest.mark.django_db
def test_tailscale_insert_and_update_devices(devices):
    """Test asset inserts and updates devices."""
    DeviceSnapshotFactory(device=None)
    updated_devices, new_devices = assets.tailscale_insert_and_update_devices(
        context=dg.build_asset_context()
    )
    assert updated_devices == 0
    assert new_devices == 1
