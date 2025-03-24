import factory
import faker

from apps.mdm.models import Device, Policy
from tests.odk_publish.factories import ProjectFactory

fake = faker.Faker()


class PolicyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Policy

    name = factory.Faker("word")
    policy_id = factory.Faker("word")
    project = factory.SubFactory(ProjectFactory)


class DeviceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Device

    policy = factory.SubFactory(PolicyFactory)
    serial_number = factory.Faker("word")
    app_user_name = factory.Faker("word")
    name = factory.Faker("word")
    device_id = factory.Sequence(lambda _: fake.unique.word())
