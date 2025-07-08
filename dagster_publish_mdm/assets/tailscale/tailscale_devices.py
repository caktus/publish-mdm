import datetime as dt

import dagster as dg
import django

from dagster_publish_mdm.resources.tailscale import TailscaleResource
from datetime import datetime, timedelta, timezone

django.setup()

from apps.tailscale.models import Device, DeviceSnapshot  # noqa: E402


@dg.asset(
    description="Get a list of tailnet devices from Tailscale",
    group_name="tailscale_assets",
)
def tailscale_device_snapshot(
    context: dg.AssetExecutionContext, tailscale: TailscaleResource
) -> dict:
    """Download a list of tailnet devices from Tailscale.

    https://tailscale.com/api#tag/devices/GET/tailnet/{tailnet}/devices
    """
    devices = tailscale.get(path=f"tailnet/{tailscale.tailnet}/devices")
    # Tailnet isn't included in the devices list, so save with the snapshot
    devices["tailnet"] = tailscale.tailnet
    context.log.info(f"Downloaded {len(devices['devices'])} devices from Tailscale")
    context.add_output_metadata({"Devices preview": devices["devices"][:2]})
    return devices


@dg.asset(description="A table of Tailscale devices over time", group_name="tailscale_assets")
def tailscale_append_device_snapshot_table(
    context: dg.AssetExecutionContext, tailscale_device_snapshot: dict
) -> list[DeviceSnapshot]:
    """Convert the Tailscale device list to a table and store in PostgreSQL."""
    device_map = dict(Device.objects.values_list("node_id", "id"))
    snapshots: list[DeviceSnapshot] = []
    for device in tailscale_device_snapshot["devices"]:
        existing_device_id = device_map.get(device["nodeId"])
        expires = dt.datetime.fromisoformat(device["expires"])
        if expires.year == 1:
            # Tailscale uses 0001-01-01T00:00:00Z to indicate no expiration
            expires = None
        snapshot = DeviceSnapshot(
            addresses=device["addresses"],
            client_version=device["clientVersion"],
            created=device["created"],
            expires=expires,
            hostname=device["hostname"],
            last_seen=device["lastSeen"],
            name=device["name"],
            node_id=device["nodeId"],
            os=device["os"],
            tags=device["tags"] if "tags" in device else None,
            update_available=device["updateAvailable"],
            user=device["user"],
            # Non-API fields
            device_id=existing_device_id,
            tailnet=tailscale_device_snapshot["tailnet"],
            raw_data=device,
            synced_at=dt.datetime.now(tz=dt.UTC),
        )
        snapshot.full_clean()
        snapshots.append(snapshot)
    DeviceSnapshot.objects.bulk_create(snapshots)
    context.log.info(f"Inserted {len(snapshots)} devices into tailscale_devicesnapshot")
    return snapshots


@dg.asset(
    group_name="tailscale_assets",
    deps=["tailscale_append_device_snapshot_table"],
    description="Updates consolidated list of Tailscale devices",
)
def tailscale_insert_and_update_devices(context: dg.AssetExecutionContext) -> tuple[int, int]:
    """Maintain a consolidated list of Tailscale devices"""
    updated_devices, new_devices = DeviceSnapshot.objects.assign_devices()
    context.log.info(
        f"Updated {updated_devices} and inserted {new_devices} devices into tailscale_device"
    )
    return updated_devices, new_devices

@dg.asset(
    group_name="tailscale_device_prunning_assets",
    deps=["tailscale_device_snapshot"],
    description="Prunes devices with no activity for over 90 days",
)
def stale_tailscale_devices(
    context: dg.AssetExecutionContext, tailscale_device_snapshot: dict) -> list:
    """Scan for old tailscale devices"""

    context.log.info("Scanning for stale devices...")

    now = datetime.now(timezone.utc)
    time_delta = now - timedelta(minutes=10)
    stale_devices = []

    for device in tailscale_device_snapshot["devices"]:
        last_seen = device.get("lastSeen")
        hostname = device.get("hostname")
        device_id = device.get("id")

        try:
            seen_time = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            if seen_time < time_delta:
                context.log.info(f"Device {hostname} last seen at {seen_time} — marking as stale.")
                stale_devices.append(device)
        except Exception as e:
            context.log.warning(f"Failed to process device {hostname}: (ID: {device_id}) {e}")

    context.add_output_metadata({"Stale Devices Preview": stale_devices[:2]})
    return stale_devices

@dg.asset(
    group_name="tailscale_device_prunning_assets",
    deps=["stale_tailscale_devices"],
    description="Prunes devices with no activity for over 90 days",
)
def pruned_stale_tailscale_devices(
    context: dg.AssetExecutionContext, 
    stale_tailscale_devices: list,
    tailscale: TailscaleResource) -> None:
    """Prunes old tailscale devices"""

    if not stale_tailscale_devices:
        context.log.info("No stale devices to prune.")
        return

    context.log.info(f"Pruning {len(stale_tailscale_devices)} devices")

    for device in stale_tailscale_devices:
        device_id = device.get("id")
        hostname = device.get("hostname")
        user = device.get("user")
        try:
            response = tailscale.delete(path=f"device/{device_id}")
            if response.status_code == 200:
                context.log.info(f"Deleted device: {hostname} (ID: {device_id}) for user: {user}")
            else:
                context.log.warning(f"Failed to delete {hostname}: (ID: {device_id}) {response.status_code} - {response.text}")
        except Exception as e:
            context.log.error(f"Error deleting device {hostname}: (ID: {device_id}) {e}")
