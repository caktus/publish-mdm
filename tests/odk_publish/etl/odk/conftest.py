import pytest


@pytest.fixture(autouse=True)
def disable_client_auth(mocker, monkeypatch):
    # Never attempt to authenticate with ODK Central
    mocker.patch("pyodk._utils.session.Auth.login")
    monkeypatch.setenv(
        "ODK_CENTRAL_CREDENTIALS",
        "base_url=https://central;username=username;password=password",
    )
