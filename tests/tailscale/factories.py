import datetime as dt

import factory
from django.utils import timezone
from faker import Faker

from apps.tailscale.models import Device, DeviceSnapshot

fake = Faker()


class DeviceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Device

    node_id = factory.Faker("uuid4")
    name = factory.Faker("name")
    last_seen = factory.Faker("date_time", tzinfo=dt.timezone.utc)
    tailnet = factory.Faker("word")
    latest_snapshot = factory.SubFactory("tests.tailscale.factories.DeviceSnapshotFactory")


class DeviceSnapshotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DeviceSnapshot

    addresses = [factory.Faker("ipv4")]
    client_version = factory.Faker("word")
    created = fake.date_time(tzinfo=dt.timezone.utc)
    expires = fake.date_time(tzinfo=dt.timezone.utc)
    hostname = factory.Faker("hostname")
    last_seen = fake.date_time(tzinfo=dt.timezone.utc)
    name = factory.Faker("word")
    node_id = factory.Faker("uuid4")
    os = "linux"
    tags = [factory.Faker("word")]
    update_available = False
    user = factory.Faker("name")
    # Non-API fields
    synced_at = timezone.now()
    raw_data = {"foo": "bar"}
    tailnet = factory.Faker("word")
