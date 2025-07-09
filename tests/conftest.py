import os
import pytest

ENV_VARS = {
    "TinyMDM": ("TINYMDM_APIKEY_PUBLIC", "TINYMDM_APIKEY_SECRET", "TINYMDM_ACCOUNT_ID"),
    "Android Enterprise": ("ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE", "ANDROID_ENTERPRISE_ID"),
}
ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE = os.path.join(
    os.path.dirname(__file__), "mdm", "android_enterprise_service_account.json"
)


@pytest.fixture(autouse=True)
def del_mdm_env_vars(monkeypatch, settings):
    """Delete environment variables for MDM API credentials, if they exist."""
    for env_vars in ENV_VARS.values():
        for var in env_vars:
            monkeypatch.delenv(var, raising=False)
            settings.SECRETS.pop(var, None)


@pytest.fixture
def set_mdm_env_vars(monkeypatch, settings):
    """Set environment variables for the currently active MDM's API credentials to fake values."""
    for var in ENV_VARS[settings.ACTIVE_MDM["name"]]:
        if var == "ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE":
            value = ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE
        else:
            value = "test"
        monkeypatch.setenv(var, value)
