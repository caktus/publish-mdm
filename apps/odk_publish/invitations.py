import structlog
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.signals import user_signed_up
from invitations.app_settings import app_settings
from invitations.utils import get_invitation_model

Invitation = get_invitation_model()
logger = structlog.getLogger(__name__)


class InvitationsAdapter(DefaultAccountAdapter):
    """Similar to django-invitation's InvitationsAdapter but overrides the post_login
    method to mark invitations as accepted and redirect to the organization's homepage.
    """

    def is_open_for_signup(self, request):
        if hasattr(request, "session") and request.session.get(
            "account_verified_email",
        ):
            return True
        elif app_settings.INVITATION_ONLY is True:
            # Site is ONLY open for invites
            return False
        else:
            # Site is open to signup
            return True

    def get_user_signed_up_signal(self):
        return user_signed_up

    def post_login(
        self, request, user, *, email_verification, signal_kwargs, email, signup, redirect_url
    ):
        from invitations.views import accept_invitation

        # If the user is being logged in after going through the accept-invite URL,
        # invitation_id will be set in the session
        invitation_id = request.session.pop("invitation_id", None)
        if invitation_id and (invitation := Invitation.objects.filter(id=invitation_id).first()):
            # Mark the invitation as accepted if not already accepted
            if not invitation.accepted:
                accept_invitation(
                    invitation=invitation,
                    request=request,
                    signal_sender=Invitation,
                )
            # Add the user to the organization
            invitation.organization.users.add(user)
            logger.info(
                "Added a user to an organization via invitation",
                user=user,
                invitation=invitation,
                organization=invitation.organization,
            )
            # Override the redirect_url
            redirect_url = invitation.organization.get_absolute_url()
        return super().post_login(
            request,
            user,
            email_verification=email_verification,
            signal_kwargs=signal_kwargs,
            email=email,
            signup=signup,
            redirect_url=redirect_url,
        )
