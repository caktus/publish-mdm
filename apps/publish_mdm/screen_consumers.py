"""WebSocket consumers for live device screen sharing.

A device running the firmware app connects to ``DeviceScreenPublisherConsumer``
authenticated by its per-device ``screen_stream_token`` (passed in the URL).
Every binary frame (a JPEG byte string) it sends is broadcast to a Channels
group named ``device-screen-<device_pk>``. The browser-side viewer connects to
``DeviceScreenViewerConsumer`` (auth via the standard Django session) and is
joined to that same group, receiving each frame and rendering it.
"""

from __future__ import annotations

import asyncio

import structlog
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.mdm.models import Device

logger = structlog.getLogger(__name__)

# Tracks how many browser viewers are watching each device (keyed by device_pk).
# Scoped to the process — sufficient with InMemoryChannelLayer.
_viewer_counts: dict[int, int] = {}
_viewer_counts_lock = asyncio.Lock()


def _group_name(device_pk: int) -> str:
    return f"device-screen-{device_pk}"


class DeviceScreenPublisherConsumer(AsyncWebsocketConsumer):
    """Receives binary screen frames from a device and fans them out."""

    async def connect(self):
        token = self.scope["url_route"]["kwargs"]["token"]
        self.device_pk = await self._lookup_device_pk(token)
        if self.device_pk is None:
            logger.warning("Device screen publish: invalid token")
            await self.close(code=4401)
            return
        self.group_name = _group_name(self.device_pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        # Notify any current viewers that the device is now publishing
        await self.channel_layer.group_send(
            self.group_name, {"type": "device.status", "status": "connected"}
        )
        logger.info("Device screen publisher connected", device_pk=self.device_pk)

    async def disconnect(self, code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_send(
                self.group_name, {"type": "device.status", "status": "disconnected"}
            )
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is None:
            return
        await self.channel_layer.group_send(
            self.group_name, {"type": "device.frame", "data": bytes_data}
        )

    async def device_frame(self, event):
        # Publisher does not need to receive its own frames
        return

    async def device_status(self, event):
        return

    async def device_stop(self, event):
        """All viewers have disconnected — tell the device to stop streaming."""
        await self.send(text_data='{"action":"stop"}')
        await self.close()

    @staticmethod
    @database_sync_to_async
    def _lookup_device_pk(token: str) -> int | None:
        if not token:
            return None
        try:
            return Device.objects.get(screen_stream_token=token).pk
        except (Device.DoesNotExist, Device.MultipleObjectsReturned):
            return None


class DeviceScreenViewerConsumer(AsyncWebsocketConsumer):
    """Streams binary screen frames to an authenticated browser session."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.device_pk = int(self.scope["url_route"]["kwargs"]["device_pk"])
        if not await self._user_can_view(user, self.device_pk):
            await self.close(code=4403)
            return
        self.group_name = _group_name(self.device_pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        count = await self._increment_viewer_count(self.device_pk, delta=1)
        logger.info("Screen viewer connected", device_pk=self.device_pk, viewer_count=count)

    async def disconnect(self, code):
        if getattr(self, "group_name", None):
            remaining = await self._increment_viewer_count(self.device_pk, delta=-1)
            logger.info(
                "Screen viewer disconnected",
                device_pk=self.device_pk,
                viewer_count=remaining,
            )
            if remaining <= 0:
                logger.info("Last viewer left, sending stop to device", device_pk=self.device_pk)
                await self.channel_layer.group_send(self.group_name, {"type": "device.stop"})
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def device_frame(self, event):
        await self.send(bytes_data=event["data"])

    async def device_status(self, event):
        await self.send(text_data=f'{{"status": "{event["status"]}"}}')

    async def device_stop(self, event):
        # Viewers don't need to act on this message — it is handled by the publisher.
        return

    @staticmethod
    @database_sync_to_async
    def _user_can_view(user, device_pk: int) -> bool:
        org_ids = list(user.get_organizations().values_list("pk", flat=True))
        if not org_ids:
            return False
        return Device.objects.filter(pk=device_pk, fleet__organization_id__in=org_ids).exists()

    async def _increment_viewer_count(self, device_pk: int, delta: int) -> int:
        """Increment/decrement the in-memory viewer count under an asyncio lock.

        Returns the new count.  Uses a module-level dict so the count is shared
        across all consumer instances in the same process (sufficient for
        InMemoryChannelLayer; with Redis channel layers a Redis counter would be
        needed for multi-process deployments).
        """
        async with _viewer_counts_lock:
            count = _viewer_counts.get(device_pk, 0) + delta
            count = max(count, 0)
            if count == 0:
                _viewer_counts.pop(device_pk, None)
            else:
                _viewer_counts[device_pk] = count
            return count
