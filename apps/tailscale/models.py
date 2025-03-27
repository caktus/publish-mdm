from django.db import models, transaction
from django.contrib import postgres
from django.db.models import Subquery, OuterRef


class Device(models.Model):
    """
    A device that is part of a tailnet.

    Source: https://tailscale.com/api#tag/tailnets/paths/~1tailnet~1{tailnet}/devices/get
    """

    node_id = models.CharField(
        max_length=128,
        help_text="The unique identifier for a device, as returned by the Tailscale API.",
        unique=True,
    )
    name = models.CharField(max_length=255, help_text="The MagicDNS name of the device.")
    last_seen = models.DateTimeField(help_text="When device was last active on the tailnet.")
    tailnet = models.CharField(max_length=255, help_text="The tailnet that the device is on.")
    latest_snapshot = models.ForeignKey(
        "DeviceSnapshot",
        on_delete=models.CASCADE,
        help_text="The most recent snapshot of the device.",
        related_name="latest_for_device",
    )

    class Meta:
        indexes = [models.Index(fields=["last_seen"])]

    def __str__(self):
        return f"{self.name} ({self.id})"


class DeviceSnapshotManager(models.Manager):
    @transaction.atomic()
    def assign_devices(self) -> tuple[int, int]:
        with transaction.atomic():
            """ """
            # Get all snapshots that don't have a device
            qs = self.get_queryset().filter(device_id=None).select_for_update()
            # Get the device ID for each snapshot's node ID
            subquery = Device.objects.filter(node_id=OuterRef("node_id"))
            qs = qs.annotate(existing_device_id=Subquery(subquery.values("id")[:1]))
            # Update the device_id field with the existing device ID
            num_updated = qs.filter(existing_device_id__isnull=False).update(
                device_id=models.F("existing_device_id")
            )
            Device.objects.filter(node_id__in=qs.values("node_id")).update(
                last_seen=models.F("latest_snapshot__last_seen")
            )
            # Create new devices for any snapshots that don't have one
            new_devices = []
            for snapshot in qs.filter(existing_device_id=None):
                device, _ = Device.objects.get_or_create(
                    node_id=snapshot.node_id,
                    defaults={
                        "name": snapshot.name,
                        "last_seen": snapshot.last_seen,
                        "tailnet": snapshot.tailnet,
                        "latest_snapshot": snapshot,
                    },
                )
                snapshot.device = device
                snapshot.save()
                new_devices.append(device)
            return num_updated, len(new_devices)


class DeviceSnapshot(models.Model):
    """
    Any computer or mobile device on a tailnet. Only a subset of the API fields
    are stored in table columns, the rest are stored as JSON in the `raw_data` field.

    Source: https://tailscale.com/api#tag/devices/GET/tailnet/{tailnet}/devices
    """

    addresses = postgres.fields.ArrayField(
        models.CharField(max_length=32),
        help_text="A list of Tailscale IP addresses for the device, including both IPv4 and IPv6.",
    )
    client_version = models.CharField(
        max_length=32,
        blank=True,
        help_text="The version of the Tailscale client software.",
    )
    created = models.DateTimeField(
        verbose_name="date added to tailnet",
        help_text="The date on which the device was added to the tailnet.",
    )
    expires = models.DateTimeField(
        null=True, blank=True, help_text="The expiration date of the device's auth key."
    )
    hostname = models.CharField(max_length=255, help_text="The machine name in the admin console.")
    last_seen = models.DateTimeField(help_text="When device was last active on the tailnet.")
    name = models.CharField(max_length=255, help_text="The MagicDNS name of the device.")
    node_id = models.CharField(max_length=128, help_text="The preferred identifier for a device.")
    os = models.CharField(
        verbose_name="operating system",
        max_length=32,
        help_text="The operating system that the device is running.",
    )
    tags = postgres.fields.ArrayField(
        models.CharField(max_length=32),
        null=True,
        blank=True,
        help_text=("Used as part of an ACL to restrict access."),
    )
    update_available = models.BooleanField(
        help_text="True if a Tailscale client version upgrade is available."
    )
    user = models.CharField(max_length=64, help_text="The user who registered the node.")

    # Non-API fields
    device = models.ForeignKey(
        "Device",
        on_delete=models.CASCADE,
        help_text="The device that this snapshot is for.",
        related_name="snapshots",
        null=True,
        blank=True,
    )
    tailnet = models.CharField(max_length=255, help_text="The tailnet that the device is on.")
    raw_data = models.JSONField(
        help_text="The full JSON response from the Tailscale API for this device."
    )
    synced_at = models.DateTimeField(help_text="When the device snapshot was synced.")

    objects = DeviceSnapshotManager()

    class Meta:
        indexes = [
            models.Index(fields=["synced_at"]),
            models.Index(fields=["tailnet"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.id}) from {self.synced_at.date()} sync"
