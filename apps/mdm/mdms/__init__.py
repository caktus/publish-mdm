from django.conf import settings
from django.utils.module_loading import import_string

from .android_enterprise import AndroidEnterprise
from .base import MDM, MDMAPIError
from .tinymdm import TinyMDM

__all__ = [
    "MDM",
    "AndroidEnterprise",
    "MDMAPIError",
    "TinyMDM",
]


def get_active_mdm_instance(organization) -> MDM | None:
    """Return an MDM instance for the given organization.

    The MDM class is resolved from ``settings.MDM_REGISTRY`` using the
    ``organization.mdm`` field as the key.  The resolved class is instantiated
    with the ``organization`` object so it can read per-org credentials.

    Returns ``None`` if the MDM name is not in the registry.
    """
    mdm_name = organization.mdm
    mdm_class_path = settings.MDM_REGISTRY.get(mdm_name)
    if not mdm_class_path:
        return None
    mdm_class = import_string(mdm_class_path)
    return mdm_class(organization=organization)
