from django.conf import settings
from django.utils.module_loading import import_string

from .android_enterprise import AndroidEnterprise
from .base import MDMAPIError
from .tinymdm import TinyMDM

__all__ = [
    "AndroidEnterprise",
    "MDMAPIError",
    "TinyMDM",
]


def get_active_mdm_class():
    return import_string(settings.ACTIVE_MDM["class"])


def get_active_mdm_instance():
    return get_active_mdm_class()()
