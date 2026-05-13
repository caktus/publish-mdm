"""Shared utilities for the MDM app."""

from django.conf import settings
from django.contrib.sites.models import Site


def get_callback_domain() -> str:
    """Return the domain used for callbacks and API URLs from Android devices.

    Resolves the domain with the following priority:

    1. ``settings.ANDROID_ENTERPRISE_CALLBACK_DOMAIN`` — explicit override,
       always wins when set (e.g. an ngrok tunnel for local development).
    2. First non-wildcard entry in ``settings.ALLOWED_HOSTS`` — works well in
       deployed environments where ``ALLOWED_HOSTS`` is set to the public
       hostname(s).
    3. Current ``django.contrib.sites`` ``Site`` object domain — ultimate
       fallback; requires the ``django.contrib.sites`` app and a correctly
       configured ``Site`` row in the database.

    Returns:
        The domain string without scheme or trailing slash (e.g.
        ``"example.com"`` or ``"abc123.ngrok-free.app"``).
    """
    domain = getattr(settings, "ANDROID_ENTERPRISE_CALLBACK_DOMAIN", "")
    if domain:
        return domain

    allowed_hosts = getattr(settings, "ALLOWED_HOSTS", [])
    for host in allowed_hosts:
        if host and host != "*":
            return host

    return Site.objects.get_current().domain
