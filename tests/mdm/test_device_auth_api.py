import base64
import hashlib
import json
import time
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.utils.timezone import now

from apps.mdm.models import DeviceAuthChallenge, DeviceBindCode, ScreenShareSession
from tests.mdm.factories import DeviceFactory


@pytest.mark.django_db
class TestDeviceAuthApi:
    register_url = "/mdm/api/devices/register-key/"
    challenge_url = "/mdm/api/devices/auth/challenge/"
    verify_url = "/mdm/api/devices/auth/verify/"

    @staticmethod
    def _new_private_key():
        return ec.generate_private_key(ec.SECP256R1())

    @staticmethod
    def _public_pem(private_key):
        return (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )

    @staticmethod
    def _sign_payload(
        private_key, challenge_id: str, request_id: str, device_id: str, timestamp: int
    ):
        payload = f"{challenge_id}.{request_id}.{device_id}.{timestamp}".encode()
        signature = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return base64.b64encode(signature).decode("ascii")

    def test_register_key_success(self, client):
        device = DeviceFactory()
        bind_code = "bind-code-123"
        DeviceBindCode.objects.create(
            device=device,
            code_hash=hashlib.sha256(bind_code.encode("utf-8")).hexdigest(),
            expires_at=now() + timedelta(minutes=10),
        )

        private_key = self._new_private_key()
        resp = client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "bind_code": bind_code,
                    "public_key_pem": self._public_pem(private_key),
                    "package_name": "com.publishmdm.agent",
                    "app_version": "1.0.0",
                }
            ),
            content_type="application/json",
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["key_version"] == 1

        device.refresh_from_db()
        assert device.auth_key_state == "active"
        assert device.auth_public_key_pem
        assert device.auth_public_key_fingerprint == body["key_fingerprint"]

    def test_register_key_without_bind_code(self, client):
        """Registration without a bind_code succeeds (dev mode)."""
        device = DeviceFactory()
        private_key = self._new_private_key()
        resp = client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "public_key_pem": self._public_pem(private_key),
                    "package_name": "com.publishmdm.agent",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        device.refresh_from_db()
        assert device.auth_key_state == "active"
        assert device.auth_key_version == 1

    def test_register_key_re_registration(self, client):
        """Re-registering a new key for an already-active device succeeds."""
        device = DeviceFactory()
        key1 = self._new_private_key()
        client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "public_key_pem": self._public_pem(key1),
                    "package_name": "com.publishmdm.agent",
                }
            ),
            content_type="application/json",
        )
        device.refresh_from_db()
        assert device.auth_key_version == 1

        key2 = self._new_private_key()
        resp = client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "public_key_pem": self._public_pem(key2),
                    "package_name": "com.publishmdm.agent",
                    "fcm_token": "fake-fcm-token-123",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        device.refresh_from_db()
        assert device.auth_key_version == 2
        assert device.fcm_token == "fake-fcm-token-123"

    def test_fcm_token_via_device_id(self, client):
        """FCM token registration via device_id (new auth) works."""
        device = DeviceFactory()
        # First register a key so auth_key_state becomes active.
        key = self._new_private_key()
        client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "public_key_pem": self._public_pem(key),
                    "package_name": "com.publishmdm.agent",
                }
            ),
            content_type="application/json",
        )
        resp = client.post(
            "/mdm/api/devices/fcm-token/",
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "fcm_token": "new-fcm-token-456",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 204
        device.refresh_from_db()
        assert device.fcm_token == "new-fcm-token-456"

    def test_register_key_invalid_bind_code(self, client):
        device = DeviceFactory()
        private_key = self._new_private_key()
        resp = client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "bind_code": "bad",
                    "public_key_pem": self._public_pem(private_key),
                    "package_name": "com.publishmdm.agent",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_challenge_and_verify_success(self, client):
        device = DeviceFactory()
        bind_code = "bind-code-xyz"
        DeviceBindCode.objects.create(
            device=device,
            code_hash=hashlib.sha256(bind_code.encode("utf-8")).hexdigest(),
            expires_at=now() + timedelta(minutes=10),
        )

        private_key = self._new_private_key()
        register_resp = client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "bind_code": bind_code,
                    "public_key_pem": self._public_pem(private_key),
                    "package_name": "com.publishmdm.agent",
                }
            ),
            content_type="application/json",
        )
        assert register_resp.status_code == 201

        request_id = "req-123"
        challenge_resp = client.post(
            self.challenge_url,
            data=json.dumps({"device_id": device.device_id, "request_id": request_id}),
            content_type="application/json",
        )
        assert challenge_resp.status_code == 200
        challenge = challenge_resp.json()

        timestamp = int(time.time())
        signature_b64 = self._sign_payload(
            private_key, challenge["challenge_id"], request_id, device.device_id, timestamp
        )

        verify_resp = client.post(
            self.verify_url,
            data=json.dumps(
                {
                    "challenge_id": challenge["challenge_id"],
                    "device_id": device.device_id,
                    "request_id": request_id,
                    "timestamp": str(timestamp),
                    "signature_b64": signature_b64,
                }
            ),
            content_type="application/json",
        )
        assert verify_resp.status_code == 200
        verify_body = verify_resp.json()
        assert verify_body["session_token"]
        assert verify_body["session_id"]

        challenge_row = DeviceAuthChallenge.objects.get(challenge_id=challenge["challenge_id"])
        assert challenge_row.used_at is not None
        assert ScreenShareSession.objects.filter(session_id=verify_body["session_id"]).exists()

    def test_verify_replay_returns_409(self, client):
        device = DeviceFactory()
        bind_code = "bind-code-replay"
        DeviceBindCode.objects.create(
            device=device,
            code_hash=hashlib.sha256(bind_code.encode("utf-8")).hexdigest(),
            expires_at=now() + timedelta(minutes=10),
        )

        private_key = self._new_private_key()
        client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "bind_code": bind_code,
                    "public_key_pem": self._public_pem(private_key),
                    "package_name": "com.publishmdm.agent",
                }
            ),
            content_type="application/json",
        )

        request_id = "req-replay"
        challenge = client.post(
            self.challenge_url,
            data=json.dumps({"device_id": device.device_id, "request_id": request_id}),
            content_type="application/json",
        ).json()

        timestamp = int(time.time())
        signature_b64 = self._sign_payload(
            private_key, challenge["challenge_id"], request_id, device.device_id, timestamp
        )
        payload = {
            "challenge_id": challenge["challenge_id"],
            "device_id": device.device_id,
            "request_id": request_id,
            "timestamp": str(timestamp),
            "signature_b64": signature_b64,
        }

        first = client.post(
            self.verify_url, data=json.dumps(payload), content_type="application/json"
        )
        second = client.post(
            self.verify_url, data=json.dumps(payload), content_type="application/json"
        )

        assert first.status_code == 200
        assert second.status_code == 409

    def test_verify_invalid_signature_returns_401(self, client):
        device = DeviceFactory()
        bind_code = "bind-code-badsig"
        DeviceBindCode.objects.create(
            device=device,
            code_hash=hashlib.sha256(bind_code.encode("utf-8")).hexdigest(),
            expires_at=now() + timedelta(minutes=10),
        )

        private_key = self._new_private_key()
        client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "bind_code": bind_code,
                    "public_key_pem": self._public_pem(private_key),
                    "package_name": "com.publishmdm.agent",
                }
            ),
            content_type="application/json",
        )

        request_id = "req-bad-signature"
        challenge = client.post(
            self.challenge_url,
            data=json.dumps({"device_id": device.device_id, "request_id": request_id}),
            content_type="application/json",
        ).json()

        other_key = self._new_private_key()
        timestamp = int(time.time())
        signature_b64 = self._sign_payload(
            other_key, challenge["challenge_id"], request_id, device.device_id, timestamp
        )

        resp = client.post(
            self.verify_url,
            data=json.dumps(
                {
                    "challenge_id": challenge["challenge_id"],
                    "device_id": device.device_id,
                    "request_id": request_id,
                    "timestamp": str(timestamp),
                    "signature_b64": signature_b64,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 401


@pytest.mark.django_db
class TestDeviceSyncPolicyApi:
    url = "/mdm/api/devices/sync-policy/"

    def test_sync_policy_success(self, client, mocker):
        device = DeviceFactory()
        mock_mdm = mocker.MagicMock()
        mocker.patch(
            "apps.mdm.views.get_active_mdm_instance",
            return_value=mock_mdm,
        )
        resp = client.post(
            self.url,
            data=json.dumps({"device_id": device.device_id}),
            content_type="application/json",
        )
        assert resp.status_code == 204
        mock_mdm.push_device_config.assert_called_once_with(device)

    def test_sync_policy_device_not_found(self, client):
        resp = client.post(
            self.url,
            data=json.dumps({"device_id": "nonexistent-device"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_sync_policy_missing_device_id(self, client):
        resp = client.post(
            self.url,
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_sync_policy_empty_body(self, client):
        resp = client.post(self.url, data="", content_type="application/json")
        assert resp.status_code == 400

    def test_sync_policy_by_serial_number(self, client, mocker):
        device = DeviceFactory(serial_number="SN-SYNC-TEST")
        mock_mdm = mocker.MagicMock()
        mocker.patch(
            "apps.mdm.views.get_active_mdm_instance",
            return_value=mock_mdm,
        )
        resp = client.post(
            self.url,
            data=json.dumps({"device_id": "SN-SYNC-TEST"}),
            content_type="application/json",
        )
        assert resp.status_code == 204
        mock_mdm.push_device_config.assert_called_once_with(device)

    def test_sync_policy_get_not_allowed(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 405

    def test_sync_policy_no_mdm_returns_204(self, client, mocker):
        device = DeviceFactory()
        mocker.patch(
            "apps.mdm.views.get_active_mdm_instance",
            return_value=None,
        )
        resp = client.post(
            self.url,
            data=json.dumps({"device_id": device.device_id}),
            content_type="application/json",
        )
        assert resp.status_code == 204
