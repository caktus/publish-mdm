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


def get_active_mdm_class(organization=None):
    if organization:
        class_string = settings.MDM_REGISTRY[organization.mdm]
    else:
        class_string = next(iter(settings.MDM_REGISTRY.values()))
    return import_string(class_string)


def get_active_mdm_instance(organization=None) -> MDM | None:
    """Return an MDM instance for the given organization.

    The MDM class is resolved from ``settings.MDM_REGISTRY`` using the
    ``organization.mdm`` field as the key.  The resolved class is instantiated
    with the ``organization`` object so it can read per-org credentials.

    Returns ``None`` if the MDM name is not in the registry.
    """
    mdm_class = get_active_mdm_class(organization)
    if mdm_class:
        try:
            return mdm_class(organization=organization)
        except ValueError:
            # MDM not configured
            pass
    return None
