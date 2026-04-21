import datetime as dt

import factory
import faker

from apps.mdm.models import (
    Device,
    DeviceSnapshot,
    DeviceSnapshotApp,
    FirmwareSnapshot,
    Fleet,
    Policy,
    PolicyApplication,
    PolicyVariable,
)
from tests.publish_mdm.factories import OrganizationFactory, ProjectFactory

fake = faker.Faker()


class PolicyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Policy

    name = factory.Faker("word")
    policy_id = factory.Faker("word")
    organization = factory.SubFactory(OrganizationFactory)


class FleetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Fleet

    name = factory.Sequence(lambda _: fake.unique.word())
    mdm_group_id = factory.Faker("pystr")
    organization = factory.SubFactory(OrganizationFactory)
    policy = factory.SubFactory(PolicyFactory)
    project = factory.SubFactory(ProjectFactory)
    enroll_qr_code = factory.django.ImageField()


class DeviceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Device

    fleet = factory.SubFactory(FleetFactory)
    serial_number = factory.Faker("word")
    app_user_name = factory.Faker("word")
    name = factory.LazyAttribute(
        lambda obj: (
            f"enterprises/test/devices/{fake.unique.pystr()}"
            if obj.fleet.organization.mdm == "Android Enterprise"
            else fake.word()
        )
    )
    device_id = factory.LazyAttribute(
        lambda obj: (
            obj.name.split("/")[-1]
            if obj.fleet.organization.mdm == "Android Enterprise"
            else fake.unique.word()
        )
    )


class DeviceSnapshotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DeviceSnapshot

    device_id = factory.Faker("word")
    name = factory.Faker("word")
    serial_number = factory.Faker("pystr")
    manufacturer = factory.Faker("company")
    os_version = factory.Faker("android_platform_token")
    battery_level = factory.Faker("pyint", min_value=0, max_value=100)
    enrollment_type = factory.Faker("random_element", elements=["fully_managed", "work_profile"])
    last_sync = factory.Faker("date_time", tzinfo=dt.UTC)
    mdm_device = factory.SubFactory(DeviceFactory)
    raw_mdm_device = factory.LazyAttribute(lambda obj: {"id": obj.device_id})
    synced_at = factory.Faker("date_time", tzinfo=dt.UTC)


class DeviceSnapshotAppFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DeviceSnapshotApp

    device_snapshot = factory.SubFactory(DeviceSnapshotFactory)
    package_name = factory.Sequence(lambda n: f"com.example.app{n}")
    app_name = factory.LazyAttribute(lambda o: fake.word() + " App")
    version_code = factory.Faker("pyint", min_value=1, max_value=9999)
    version_name = factory.Faker("numerify", text="##.##.##")


class FirmwareSnapshotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FirmwareSnapshot

    device_identifier = factory.Faker("pystr")
    serial_number = factory.Faker("pystr")
    version = factory.Faker("word")
    raw_data = factory.LazyAttribute(lambda obj: {"serialNumber": obj.serial_number})
    device = factory.SubFactory(DeviceFactory)


class PolicyApplicationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PolicyApplication

    policy = factory.SubFactory(PolicyFactory)
    package_name = factory.Sequence(lambda n: f"com.example.app{n}")
    install_type = "FORCE_INSTALLED"
    disabled = False
    order = factory.Sequence(lambda n: n + 1)


class PolicyVariableFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PolicyVariable

    policy = factory.SubFactory(PolicyFactory)
    key = factory.Sequence(lambda n: f"var_key_{n}")
    value = factory.Faker("word")
    scope = "policy"
