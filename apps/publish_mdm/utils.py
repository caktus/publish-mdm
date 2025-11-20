import os
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.http import QueryDict
from django.shortcuts import resolve_url


def get_secret(key):
    """Get a value either from the SECRETS setting (populated from a file) or
    from environment variables.
    """
    return settings.SECRETS.get(key, os.getenv(key))


def get_login_url(
    next, login_url=None, redirect_field_name=REDIRECT_FIELD_NAME, force_oauth_flow=True
):
    """
    Get a login URL that would redirect the user to the login page, passing the
    given 'next' page.

    Like django.contrib.auth.views.redirect_to_login, but adds force_oauth_flow
    and returns a URL instead of a HttpResponseRedirect object.

    force_oauth_flow will force the user to go through the Google OAuth flow
    even if they had logged in before.
    """
    resolved_url = resolve_url(login_url or settings.LOGIN_URL)

    login_url_parts = list(urlsplit(resolved_url))
    if redirect_field_name or force_oauth_flow:
        querystring = QueryDict(login_url_parts[3], mutable=True)
        if force_oauth_flow:
            querystring["auth_params"] = "prompt=select_account consent"
        if redirect_field_name:
            querystring[redirect_field_name] = next
        login_url_parts[3] = querystring.urlencode(safe="/")

    return urlunsplit(login_url_parts)
