import pytest
from allauth.account.signals import user_signed_up
from django.urls import reverse
from invitations.views import accept_invitation

from apps.publish_mdm.invitations import InvitationsAdapter

from tests.publish_mdm.factories import OrganizationInvitationFactory
from tests.users.factories import UserFactory


@pytest.mark.django_db
class TestInvitationsAdapter:
    @pytest.fixture
    def user(self):
        return UserFactory()

    @pytest.fixture
    def adapter(self):
        return InvitationsAdapter()

    def test_allow_signup_without_an_invitation(self, rf, adapter, settings):
        """When the INVITATIONS_INVITATION_ONLY setting is False (the default),
        the adapter should allow signup even if not coming from an invitation.
        """
        request = rf.get("/")
        settings.INVITATIONS_INVITATION_ONLY = False
        assert adapter.is_open_for_signup(request)

    def test_require_invitation_for_signup(self, rf, adapter, settings):
        """When the INVITATIONS_INVITATION_ONLY setting is True,
        the adapter should only allow signup if coming from an invitation.
        """
        request = rf.get("/")
        settings.INVITATIONS_INVITATION_ONLY = True
        assert not adapter.is_open_for_signup(request)

        # The adapter checks for a "account_verified_email" key in the session
        # to determine if the signup is through an invitation
        request.session = {"account_verified_email": "test@test.com"}
        assert adapter.is_open_for_signup(request)

    def test_get_user_signed_up_signal(self, adapter):
        assert adapter.get_user_signed_up_signal() == user_signed_up

    def test_post_login_with_invitation(self, rf, user, adapter, mocker):
        """Ensure if the user is logging in after accepting an invite the invitation
        is marked accepted and the user is redirected to the organization's homepage.
        """
        invitation = OrganizationInvitationFactory(accepted=False)
        request = rf.get("/")
        request.user = user
        request._messages = mocker.MagicMock()
        # If coming from an invitation the invitation ID will be in the session
        request.session = {"invitation_id": invitation.id}
        mock_accept_invitation = mocker.patch(
            "invitations.views.accept_invitation", wraps=accept_invitation
        )
        response = adapter.post_login(
            request,
            user,
            email_verification=None,
            signal_kwargs=None,
            email=None,
            signup=False,
            redirect_url=None,
        )
        # Check the redirect
        assert response.status_code == 302
        assert response.url == invitation.organization.get_absolute_url()
        # Ensure accept_invitation() was called and the invitation was updated
        mock_accept_invitation.assert_called_once()
        invitation.refresh_from_db()
        assert invitation.accepted
        # The invitation ID should be removed from the session
        assert "invitation_id" not in request.session

    def test_post_login_with_accepted_invitation(self, rf, user, adapter, mocker):
        invitation = OrganizationInvitationFactory(accepted=True)
        request = rf.get("/")
        request.user = user
        request._messages = mocker.MagicMock()
        # If coming from an invitation the invitation ID will be in the session
        request.session = {"invitation_id": invitation.id}
        mock_accept_invitation = mocker.patch(
            "invitations.views.accept_invitation", wraps=accept_invitation
        )
        response = adapter.post_login(
            request,
            user,
            email_verification=None,
            signal_kwargs=None,
            email=None,
            signup=False,
            redirect_url=None,
        )
        # Check the redirect
        assert response.status_code == 302
        assert response.url == invitation.organization.get_absolute_url()
        # Ensure accept_invitation() was not called
        mock_accept_invitation.assert_not_called()
        # The invitation ID should be removed from the session
        assert "invitation_id" not in request.session

    def test_post_login_without_invitation(self, rf, user, adapter, mocker, settings):
        """Ensure users can still log in without an invitation ID in the session."""
        request = rf.get("/")
        request.user = user
        request.session = {}
        request._messages = mocker.MagicMock()
        response = adapter.post_login(
            request,
            user,
            email_verification=None,
            signal_kwargs={},
            email=None,
            signup=False,
            redirect_url=None,
        )
        assert response.status_code == 302
        assert response.url == reverse(settings.LOGIN_REDIRECT_URL)
