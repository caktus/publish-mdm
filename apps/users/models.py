from django.contrib.auth.models import AbstractUser

from allauth.socialaccount.models import SocialToken


class User(AbstractUser):
    """Custom user model."""

    def get_google_social_token(self) -> SocialToken | None:
        """Return the user's Google social token for use with the Google Sheets API."""
        return SocialToken.objects.filter(account__user=self, account__provider="google").first()
