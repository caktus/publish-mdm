import pytest

TINYMDM_ENV_VARS = ("TINYMDM_APIKEY_PUBLIC", "TINYMDM_APIKEY_SECRET", "TINYMDM_ACCOUNT_ID")


@pytest.fixture(autouse=True)
def del_tinymdm_env_vars(monkeypatch):
    """Delete environment variables for TinyMDM API credentials, if they exist."""
    for var in TINYMDM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def set_tinymdm_env_vars(monkeypatch):
    """Set environment variables for TinyMDM API credentials to fake values."""
    for var in TINYMDM_ENV_VARS:
        monkeypatch.setenv(var, "test")
