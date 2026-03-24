"""
Security regression tests for the publish_mdm app.

VULN-002 (HUNT-003): SSRF via user-supplied CentralServer.base_url
  - CentralServerForm.clean() passes the user-supplied base_url directly to
    requests.post() without validating the scheme or hostname.  An authenticated
    org member can supply an internal URL (e.g. http://169.254.169.254/) and
    the server will make an outbound request on their behalf.
"""

import pytest
from django.urls import reverse

from tests.publish_mdm.factories import OrganizationFactory, UserFactory

# ---------------------------------------------------------------------------
# VULN-002: SSRF via CentralServer.base_url
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCentralServerSSRF:
    """VULN-002: base_url must be validated before requests.post() is called."""

    @pytest.fixture
    def user(self, client):
        user = UserFactory()
        user.save()
        client.force_login(user)
        return user

    @pytest.fixture
    def organization(self, user):
        org = OrganizationFactory()
        org.users.add(user)
        return org

    @pytest.fixture
    def url(self, organization):
        return reverse("publish_mdm:add-central-server", args=[organization.slug])

    def test_private_ip_base_url_rejected(self, client, url, user, organization, mocker, settings):
        """Supplying an RFC-1918 / link-local address as base_url must be rejected
        without making any outbound HTTP request.

        Previously CentralServerForm.clean() called requests.post() on the raw URL,
        allowing SSRF to internal services such as the AWS metadata endpoint.
        """
        settings.DEBUG = False
        mock_post = mocker.patch("apps.publish_mdm.forms.requests.post")

        response = client.post(
            url,
            data={
                "base_url": "http://169.254.169.254/latest/meta-data/",
                "username": "attacker@example.com",
                "password": "password",
            },
        )

        # The form must reject the request before making any outbound call
        assert response.status_code == 200  # form re-rendered with errors
        mock_post.assert_not_called()
        assert "base_url" in response.context["form"].errors

    def test_http_base_url_rejected(self, client, url, user, organization, mocker, settings):
        """Plain http:// URLs must be rejected when DEBUG is False."""
        settings.DEBUG = False
        mock_post = mocker.patch("apps.publish_mdm.forms.requests.post")

        response = client.post(
            url,
            data={
                "base_url": "http://example.com",
                "username": "user@example.com",
                "password": "password",
            },
        )

        assert response.status_code == 200
        mock_post.assert_not_called()
        assert "base_url" in response.context["form"].errors

    def test_http_base_url_allowed_in_debug(
        self, client, url, user, organization, mocker, settings
    ):
        """All URL checks are skipped when DEBUG is True (development).

        Allows developers to use http:// or private-IP Central instances locally.
        """
        settings.DEBUG = True
        mock_post = mocker.patch(
            "apps.publish_mdm.forms.requests.post",
            return_value=mocker.Mock(status_code=200),
        )

        response = client.post(
            url,
            data={
                "base_url": "http://localhost:8383",
                "username": "user@example.com",
                "password": "password",
            },
        )

        # All checks are skipped in DEBUG mode; requests.post should be called
        # and the form submits successfully (redirects)
        assert response.status_code == 302
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert call_url.startswith("http://localhost:8383")

    def test_private_ip_allowed_in_debug(self, client, url, user, organization, mocker, settings):
        """Private/reserved IP addresses are allowed when DEBUG is True (development)."""
        settings.DEBUG = True
        mock_post = mocker.patch(
            "apps.publish_mdm.forms.requests.post",
            return_value=mocker.Mock(status_code=200),
        )

        response = client.post(
            url,
            data={
                "base_url": "http://192.168.1.10:8383",
                "username": "user@example.com",
                "password": "password",
            },
        )

        assert response.status_code == 302
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert call_url.startswith("http://192.168.1.10:8383")

    def test_loopback_base_url_rejected(self, client, url, user, organization, mocker, settings):
        """Loopback addresses (127.x.x.x) must be rejected when DEBUG is False."""
        settings.DEBUG = False
        mock_post = mocker.patch("apps.publish_mdm.forms.requests.post")

        response = client.post(
            url,
            data={
                "base_url": "https://127.0.0.1/",
                "username": "user@example.com",
                "password": "password",
            },
        )

        assert response.status_code == 200
        mock_post.assert_not_called()
        assert "base_url" in response.context["form"].errors

    def test_valid_https_url_proceeds_to_connection_check(
        self, client, url, user, organization, mocker
    ):
        """A legitimate https:// public URL should still attempt the ODK login check."""
        mock_post = mocker.patch(
            "apps.publish_mdm.forms.requests.post",
            return_value=mocker.Mock(status_code=200),
        )

        client.post(
            url,
            data={
                "base_url": "https://odk.example.com",
                "username": "user@example.com",
                "password": "password",
            },
        )

        # requests.post should have been called for the valid URL
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert call_url.startswith("https://odk.example.com")
