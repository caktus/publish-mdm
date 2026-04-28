import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser

from apps.publish_mdm.screen_consumers import (
    DeviceScreenPublisherConsumer,
    DeviceScreenViewerConsumer,
)
from tests.mdm.factories import DeviceFactory, FleetFactory
from tests.publish_mdm.factories import OrganizationFactory
from tests.users.factories import UserFactory


@database_sync_to_async
def _create_device_with_token(token, org=None):
    if org is None:
        org = OrganizationFactory()
    fleet = FleetFactory(organization=org)
    return DeviceFactory(fleet=fleet, screen_stream_token=token)


@database_sync_to_async
def _create_user_in_org(org):
    user = UserFactory()
    user.save()
    org.users.add(user)
    return user


@pytest.mark.django_db(transaction=True)
class TestDeviceScreenPublisherConsumer:
    """Tests for the device-side screen publisher WebSocket."""

    @pytest.mark.asyncio
    async def test_valid_token_connects(self):
        await _create_device_with_token("pub-tok-1")
        communicator = WebsocketCommunicator(
            DeviceScreenPublisherConsumer.as_asgi(),
            "/ws/devices/screen-publish/pub-tok-1/",
        )
        communicator.scope["url_route"] = {"kwargs": {"token": "pub-tok-1"}}
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self):
        communicator = WebsocketCommunicator(
            DeviceScreenPublisherConsumer.as_asgi(),
            "/ws/devices/screen-publish/bad-token/",
        )
        communicator.scope["url_route"] = {"kwargs": {"token": "bad-token"}}
        connected, code = await communicator.connect()
        assert not connected
        assert code == 4401

    @pytest.mark.asyncio
    async def test_empty_token_rejected(self):
        communicator = WebsocketCommunicator(
            DeviceScreenPublisherConsumer.as_asgi(),
            "/ws/devices/screen-publish//",
        )
        communicator.scope["url_route"] = {"kwargs": {"token": ""}}
        connected, code = await communicator.connect()
        assert not connected
        assert code == 4401


@pytest.mark.django_db(transaction=True)
class TestDeviceScreenViewerConsumer:
    """Tests for the browser-side screen viewer WebSocket."""

    @pytest.mark.asyncio
    async def test_authenticated_user_connects(self):
        org = await database_sync_to_async(OrganizationFactory)()
        device = await _create_device_with_token("view-tok-1", org=org)
        user = await _create_user_in_org(org)
        device_pk = await database_sync_to_async(lambda: device.pk)()

        communicator = WebsocketCommunicator(
            DeviceScreenViewerConsumer.as_asgi(),
            f"/ws/devices/{device_pk}/screen-view/",
        )
        communicator.scope["url_route"] = {"kwargs": {"device_pk": str(device_pk)}}
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_unauthenticated_rejected(self):
        communicator = WebsocketCommunicator(
            DeviceScreenViewerConsumer.as_asgi(),
            "/ws/devices/1/screen-view/",
        )
        communicator.scope["url_route"] = {"kwargs": {"device_pk": "1"}}
        communicator.scope["user"] = AnonymousUser()
        connected, code = await communicator.connect()
        assert not connected
        assert code == 4401

    @pytest.mark.asyncio
    async def test_wrong_org_rejected(self):
        org1 = await database_sync_to_async(OrganizationFactory)()
        org2 = await database_sync_to_async(OrganizationFactory)()
        device = await _create_device_with_token("view-tok-2", org=org1)
        user = await _create_user_in_org(org2)  # user is in org2, not org1
        device_pk = await database_sync_to_async(lambda: device.pk)()

        communicator = WebsocketCommunicator(
            DeviceScreenViewerConsumer.as_asgi(),
            f"/ws/devices/{device_pk}/screen-view/",
        )
        communicator.scope["url_route"] = {"kwargs": {"device_pk": str(device_pk)}}
        communicator.scope["user"] = user
        connected, code = await communicator.connect()
        assert not connected
        assert code == 4403
