import base64
from functools import cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.functional import cached_property
from django.utils.text import get_text_list

from infisical_sdk import InfisicalSDKClient
from infisical_sdk.api_types import KmsKey, SymmetricEncryption
from infisical_sdk.infisical_requests import APIError


class InfisicalKMS:
    @cached_property
    def client(self) -> InfisicalSDKClient:
        """Create an Infisical API client."""
        # First ensure all the settings needed for API access are available
        missing_settings = []
        for setting in ("INFISICAL_HOST", "INFISICAL_TOKEN", "INFISICAL_PROJECT_ID"):
            if not getattr(settings, setting, None):
                missing_settings.append(setting)
        if missing_settings:
            raise ImproperlyConfigured(
                f'{get_text_list(missing_settings, "and")} must be defined in settings.'
            )
        # Create the client
        return InfisicalSDKClient(settings.INFISICAL_HOST, settings.INFISICAL_TOKEN)

    @cache
    def get_key(self, key_name: str, can_create: bool = True) -> KmsKey:
        """Get or create a key with the provided name."""
        try:
            return self.client.kms.get_key_by_name(key_name, settings.INFISICAL_PROJECT_ID)
        except APIError as e:
            if e.status_code == 404 and can_create:
                # The key does not exist. Create it
                return self.client.kms.create_key(
                    key_name, settings.INFISICAL_PROJECT_ID, SymmetricEncryption.AES_GCM_256
                )
            raise

    def encrypt(self, key_name: str, string: str) -> str:
        """Encrypt a string."""
        key = self.get_key(key_name)
        return self.client.kms.encrypt_data(key.id, base64.b64encode(string.encode()).decode())

    def decrypt(self, key_name: str, encrypted_string: str) -> str:
        """Decrypt a string."""
        key = self.get_key(key_name)
        return base64.b64decode(self.client.kms.decrypt_data(key.id, encrypted_string)).decode()


kms_api = InfisicalKMS()
