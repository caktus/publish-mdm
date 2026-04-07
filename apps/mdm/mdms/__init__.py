from django.conf import settings
from django.utils.module_loading import import_string

from .android_enterprise import AndroidEnterprise
from .base import MDM, MDMAPIError
from .tinymdm import TinyMDM

__all__ = [
    "AndroidEnterprise",
    "MDM",
    "MDMAPIError",
    "TinyMDM",
]

# MDM name → class mapping (used when no org is provided for backwards compatibility)
_MDM_CLASS_MAP = {
    "TinyMDM": TinyMDM,
    "Android Enterprise": AndroidEnterprise,
}


def get_active_mdm_class():
    return import_string(settings.ACTIVE_MDM["class"])


def get_active_mdm_instance(organization=None) -> MDM | None:
    """Return an MDM instance for the given organization, or the globally-configured MDM.

    When ``organization`` is provided its ``mdm`` field determines the MDM class.
    TinyMDM instances receive the org's stored API credentials, falling back to the
    environment variables if the org credentials are not set.

    When ``organization`` is ``None`` the behaviour is unchanged from before: the MDM
    class is read from ``settings.ACTIVE_MDM``.
    """
    if organization is not None:
        from apps.mdm.models import MDMChoices

        mdm_name = organization.mdm
        if mdm_name == MDMChoices.TINYMDM:
            return TinyMDM(
                apikey_public=organization.tinymdm_apikey_public or None,
                apikey_secret=organization.tinymdm_apikey_secret or None,
                account_id=organization.tinymdm_account_id or None,
            )
        if mdm_name == MDMChoices.ANDROID_ENTERPRISE:
            return AndroidEnterprise()
        return None
    # Fall back to the global ACTIVE_MDM setting for backwards compatibility
    return get_active_mdm_class()()
