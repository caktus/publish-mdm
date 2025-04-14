import pytest
import datetime as dt
from django.utils import timezone

from apps.tailscale.models import DeviceSnapshot, Device

from .factories import DeviceSnapshotFactory, DeviceFactory


class TestDevice:
    def test_str(self):
        device = DeviceFactory.build(name="device_name", id=5)
        assert str(device) == "device_name (5)"


class TestDeviceSnapshot:
    def test_str(self):
        snapshot = DeviceSnapshotFactory.build(
            name="name", id=5, synced_at=dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc)
        )
        assert str(snapshot) == "name (5) from 2021-01-01 sync"


@pytest.mark.django_db
class TestAssignDevices:
    def test_device_created_for_new_node_id(self):
        """A snapshot without a device should create a new device"""
        snapshot = DeviceSnapshotFactory(device=None)
        assert Device.objects.count() == 0
        DeviceSnapshot.objects.assign_devices()
        assert Device.objects.count() == 1
        snapshot.refresh_from_db()
        assert snapshot.device is not None
        assert snapshot.node_id == snapshot.device.node_id

    def test_latest_snapshot_linked(self):
        """The device should have the snapshot as its latest_snapshot"""
        device = DeviceFactory()
        snapshot = DeviceSnapshotFactory(node_id=device.node_id, device=device)
        DeviceSnapshot.objects.assign_devices()
        device.refresh_from_db()
        assert device.latest_snapshot == snapshot

    def test_device_updated_for_existing_node_id(self):
        """The most recent snapshot should be linked to the device"""
        now = timezone.now()
        device = DeviceFactory(latest_snapshot__synced_at=now - dt.timedelta(days=10))
        snap1 = DeviceSnapshotFactory(node_id=device.node_id, device=device, synced_at=now)
        snap2 = DeviceSnapshotFactory(
            node_id=device.node_id, device=device, synced_at=now - dt.timedelta(days=15)
        )
        assert snap1.synced_at > snap2.synced_at
        DeviceSnapshot.objects.assign_devices()
        device.refresh_from_db()
        assert device.latest_snapshot == snap1
