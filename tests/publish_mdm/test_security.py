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

    def test_private_ip_base_url_rejected(self, client, url, user, organization, mocker):
        """Supplying an RFC-1918 / link-local address as base_url must be rejected
        without making any outbound HTTP request.

        Previously CentralServerForm.clean() called requests.post() on the raw URL,
        allowing SSRF to internal services such as the AWS metadata endpoint.
        """
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

    def test_http_base_url_rejected(self, client, url, user, organization, mocker):
        """Plain http:// URLs must be rejected; only https:// is allowed."""
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

    def test_loopback_base_url_rejected(self, client, url, user, organization, mocker):
        """Loopback addresses (127.x.x.x) must be rejected."""
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


# ---------------------------------------------------------------------------
# VULN-003: Sentry send_default_pii defaults to True
# ---------------------------------------------------------------------------


class TestSentryPIIDefault:
    """VULN-003: SENTRY_SEND_DEFAULT_PII must default to False.

    When the environment variable is absent the deploy settings must opt out of
    sending PII to Sentry, not opt in.  An operator who wants PII sent must
    explicitly set SENTRY_SEND_DEFAULT_PII=True.
    """

    def test_sentry_pii_default_is_false(self, monkeypatch):
        """With no env var, SENTRY_SEND_DEFAULT_PII must resolve to False.

        The pattern is:
            SENTRY_SEND_DEFAULT_PII = os.getenv("SENTRY_SEND_DEFAULT_PII", "<default>") == "True"
        The second argument to os.getenv is the default; it must be "False".
        """
        import ast
        from pathlib import Path

        deploy_path = Path("config/settings/deploy.py")
        source = deploy_path.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "SENTRY_SEND_DEFAULT_PII"
                    for t in node.targets
                )
            ):
                continue
            # node.value is: Compare(Call(getenv, [..., default]), [Eq], [Constant("True")])
            # Drill into the Call node to find the second arg (the default)
            for subnode in ast.walk(node.value):
                if (
                    isinstance(subnode, ast.Call)
                    and len(subnode.args) == 2
                    and isinstance(subnode.args[1], ast.Constant)
                ):
                    default_val = subnode.args[1].value
                    assert default_val == "False", (
                        f"SENTRY_SEND_DEFAULT_PII os.getenv default must be 'False', "
                        f"but found '{default_val}'. "
                        "Set SENTRY_SEND_DEFAULT_PII=True explicitly to opt in."
                    )
                    return
        raise AssertionError(
            "Could not find SENTRY_SEND_DEFAULT_PII assignment in config/settings/deploy.py"
        )
