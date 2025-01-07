import pytest


@pytest.fixture(autouse=True)
def disable_client_auth(mocker, settings):
    # Never attempt to authenticate with ODK Central
    mocker.patch("pyodk._utils.session.Auth.login")
    settings.ODK_CENTRAL_USERNAME = "username"
    settings.ODK_CENTRAL_PASSWORD = "password"
