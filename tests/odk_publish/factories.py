from typing import Generic, TypeVar

import factory

from apps.odk_publish import models
from tests.users.factories import UserFactory

T = TypeVar("T")


class BaseMetaFactory(Generic[T], factory.base.FactoryMetaClass):
    """Typing helper to return the Model class from the factory.

    Source: https://github.com/FactoryBoy/factory_boy/issues/468#issuecomment-1151633557
    """

    def __call__(cls, *args, **kwargs) -> T:
        return super().__call__(*args, **kwargs)


class CentralServerFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[models.CentralServer]
):
    class Meta:
        model = models.CentralServer

    base_url = factory.Faker("url")


class TemplateVariableFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[models.TemplateVariable]
):
    class Meta:
        model = models.TemplateVariable

    name = factory.Faker("word")


class ProjectFactory(factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[models.Project]):
    class Meta:
        model = models.Project

    central_id = factory.Sequence(lambda n: n)
    central_server = factory.SubFactory(CentralServerFactory)
    name = factory.Faker("word")


class AppUserFactory(factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[models.AppUser]):
    class Meta:
        model = models.AppUser

    central_id = factory.Sequence(lambda n: n)
    project = factory.SubFactory(ProjectFactory)
    name = factory.Faker("word")


class FormTemplateFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[models.FormTemplate]
):
    class Meta:
        model = models.FormTemplate

    form_id_base = factory.Faker("word")
    project = factory.SubFactory(ProjectFactory)
    title_base = factory.Faker("word")


class AppUserFormTemplateFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[models.AppUserFormTemplate]
):
    class Meta:
        model = models.AppUserFormTemplate

    app_user = factory.SubFactory(AppUserFactory)
    form_template = factory.SubFactory(FormTemplateFactory)


class FormTemplateVersionFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[models.FormTemplateVersion]
):
    class Meta:
        model = models.FormTemplateVersion

    form_template = factory.SubFactory(FormTemplateFactory)
    user = factory.SubFactory(UserFactory)
    file = factory.django.FileField()
    version = factory.Sequence(lambda n: f"v{n}")


class AppUserFormVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.AppUserFormVersion

    app_user_form_template = factory.SubFactory(AppUserFormTemplateFactory)
    form_template_version = factory.SubFactory(FormTemplateVersionFactory)
    file = factory.django.FileField()


class AppUserTemplateVariableFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.AppUserTemplateVariable

    app_user = factory.SubFactory(AppUserFactory)
    template_variable = factory.SubFactory(TemplateVariableFactory)
    value = factory.Faker("word")


class ProjectAttachmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProjectAttachment

    name = factory.Faker("word")
    project = factory.SubFactory(ProjectFactory)
    file = factory.django.FileField()
