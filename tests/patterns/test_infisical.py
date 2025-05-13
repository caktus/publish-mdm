import base64

import pytest
from django.core.exceptions import ImproperlyConfigured
from infisical_sdk.api_types import KmsKey
from infisical_sdk.infisical_requests import APIError

from apps.patterns.infisical import InfisicalKMS


class TestInfisicalKMS:
    """Test the Infisical KMS integration for encrypting and decrypting secrets."""

    @pytest.fixture
    def set_infisical_settings(self, settings):
        settings.INFISICAL_HOST = "http://test"
        settings.INFISICAL_TOKEN = "token"
        settings.INFISICAL_PROJECT_ID = "projectid"

    @pytest.fixture
    def key_json(self, set_infisical_settings, settings):
        # Mock JSON response for successfully getting or creating a key in Infisical
        return {
            "key": {
                "id": "3c90c3cc-0d44-4b50-8888-8dd25736052a",
                "description": "test key",
                "isDisabled": False,
                "orgId": "3c90c3cc-0d44-4b50-8888-8dd25736052a",
                "name": "testkey",
                "createdAt": "2023-11-07T05:31:56Z",
                "updatedAt": "2023-11-07T05:31:56Z",
                "projectId": settings.INFISICAL_PROJECT_ID,
                "keyUsage": "encrypt-decrypt",
                "version": 1,
                "encryptionAlgorithm": "aes-256-gcm",
            }
        }

    def test_missing_settings(self, set_infisical_settings, settings):
        """Ensure an ImproperlyConfigured exception is raised when getting the API
        client if any of the INFISICAL_* settings is missing.
        """
        settings.INFISICAL_HOST = None
        kms_api = InfisicalKMS()
        with pytest.raises(
            ImproperlyConfigured, match="INFISICAL_HOST must be defined in settings."
        ):
            kms_api.client
        settings.INFISICAL_TOKEN = None
        with pytest.raises(
            ImproperlyConfigured,
            match="INFISICAL_HOST and INFISICAL_TOKEN must be defined in settings.",
        ):
            kms_api.client

    def test_get_key(self, requests_mock, set_infisical_settings, settings, key_json):
        """Ensure calling get_key() with a valid key name returns a KmsKey object."""
        kms_api = InfisicalKMS()
        requests_mock.get(
            f"/api/v1/kms/keys/key-name/testkey?projectId={settings.INFISICAL_PROJECT_ID}",
            json=key_json,
        )
        key = kms_api.get_key("testkey")
        assert isinstance(key, KmsKey)
        assert key.id == key_json["key"]["id"]

    def test_get_notexistent_key_but_can_create(
        self, requests_mock, set_infisical_settings, settings, key_json
    ):
        """Ensure calling get_key() with a key name that does not exist but with
        can_create=True creates the key in Infisical and returns the KmsKey object.
        """
        kms_api = InfisicalKMS()
        requests_mock.get(
            f"/api/v1/kms/keys/key-name/testkey?projectId={settings.INFISICAL_PROJECT_ID}",
            status_code=404,
        )
        create_key_request = requests_mock.post("/api/v1/kms/keys", json=key_json)
        key = kms_api.get_key("testkey", can_create=True)
        assert isinstance(key, KmsKey)
        assert key.id == key_json["key"]["id"]
        assert create_key_request.called_once

    def test_get_notexistent_key_and_cant_create(
        self, requests_mock, set_infisical_settings, settings, key_json
    ):
        """Ensure calling get_key() with a key name that does not exist and with
        can_create=False does not attempt to create the key in Infisical.
        """
        kms_api = InfisicalKMS()
        requests_mock.get(
            f"/api/v1/kms/keys/key-name/testkey?projectId={settings.INFISICAL_PROJECT_ID}",
            status_code=404,
        )
        create_key_request = requests_mock.post("/api/v1/kms/keys", json=key_json)
        with pytest.raises(APIError):
            kms_api.get_key("testkey", can_create=False)
        assert create_key_request.call_count == 0

    def test_encrypt(self, requests_mock, set_infisical_settings, settings, key_json):
        """Test encrypting."""
        kms_api = InfisicalKMS()
        requests_mock.get(
            f"/api/v1/kms/keys/key-name/testkey?projectId={settings.INFISICAL_PROJECT_ID}",
            json=key_json,
        )
        encrypt_json = {"ciphertext": "encrypted"}
        requests_mock.post(f'/api/v1/kms/keys/{key_json["key"]["id"]}/encrypt', json=encrypt_json)
        result = kms_api.encrypt("testkey", "encrypt me")
        assert result == encrypt_json["ciphertext"]

    def test_decrypt(self, requests_mock, set_infisical_settings, settings, key_json):
        """Test Decrypting."""
        kms_api = InfisicalKMS()
        requests_mock.get(
            f"/api/v1/kms/keys/key-name/testkey?projectId={settings.INFISICAL_PROJECT_ID}",
            json=key_json,
        )
        expected = "decrypted"
        decrypt_json = {
            "plaintext": base64.b64encode(expected.encode()).decode(),
        }
        requests_mock.post(f'/api/v1/kms/keys/{key_json["key"]["id"]}/decrypt', json=decrypt_json)
        result = kms_api.decrypt("testkey", "decrypt me")
        assert result == expected
