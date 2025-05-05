import factory
import faker

from allauth.socialaccount.models import SocialAccount, SocialToken

from apps.users.models import User

fake = faker.Faker()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("email",)
        skip_postgeneration_save = True

    email = factory.Faker("email")
    is_staff = False
    is_active = True
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    username = factory.Sequence(lambda _: fake.unique.user_name())

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        """Generate a password for the user."""
        password = (
            extracted
            if extracted
            else factory.Faker(
                "password",
                length=42,
                special_chars=True,
                digits=True,
                upper_case=True,
                lower_case=True,
            ).evaluate(None, None, extra={"locale": None})
        )
        self.set_password(password)

    @factory.post_generation
    def socialaccount(self, create, extracted, **kwargs):
        """Create a social account for the user."""
        if not create:
            return
        SocialTokenFactory(account__user=self, account__uid=fake.random_number())


class SocialAccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SocialAccount

    provider = "google"


class SocialTokenFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SocialToken

    account = factory.SubFactory(SocialAccountFactory)
