from django.contrib.auth.models import AbstractUser

from allauth.socialaccount.models import SocialToken


class User(AbstractUser):
    """Custom user model."""

    def get_google_social_token(self) -> SocialToken | None:
        """Return the user's Google social token for use with the Google Sheets API."""
        # Prefer a SocialToken that has a token_secret (refresh token)
        return (
            SocialToken.objects.filter(account__user=self, account__provider="google")
            .order_by("-token_secret")
            .first()
        )

    def get_organizations(self):
        from apps.publish_mdm.models import Organization

        if self.is_superuser:
            return Organization.objects.order_by("created_at")
        return self.organizations.order_by("created_at")
