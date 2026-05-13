import base64
import hashlib
import json
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.utils.timezone import now

from apps.mdm.attestation import AttestationError
from apps.mdm.models import (
    DeviceAttestationNonce,
    DeviceAuthChallenge,
    ScreenShareSession,
)
from tests.mdm.factories import DeviceFactory


@pytest.mark.django_db
class TestDeviceAuthApi:
    register_url = "/mdm/api/devices/register-key/"
    nonce_url = "/mdm/api/devices/attestation/nonce/"
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

    # -------------------------------------------------------------------------
    # Attestation nonce endpoint
    # -------------------------------------------------------------------------

    def test_attestation_nonce_success(self, client):
        device = DeviceFactory()
        resp = client.post(
            self.nonce_url,
            data=json.dumps({"device_id": device.device_id}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "nonce" in body
        assert len(body["nonce"]) == 64  # 32 bytes hex
        assert "expires_at" in body
        assert DeviceAttestationNonce.objects.filter(device=device, nonce=body["nonce"]).exists()

    def test_attestation_nonce_device_not_found(self, client):
        resp = client.post(
            self.nonce_url,
            data=json.dumps({"device_id": "nonexistent"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_attestation_nonce_missing_device_id(self, client):
        resp = client.post(
            self.nonce_url,
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_attestation_nonce_empty_body(self, client):
        resp = client.post(self.nonce_url, data="", content_type="application/json")
        assert resp.status_code == 400

    # -------------------------------------------------------------------------
    # Register key -- direct public key (unattested / emulator mode)
    # -------------------------------------------------------------------------

    def test_register_key_success_unattested(self, client):
        """Registration with direct public_key_pem (no attestation) succeeds."""
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
        body = resp.json()
        assert body["key_version"] == 1
        assert "key_fingerprint" in body
        assert "device_token" not in body

        device.refresh_from_db()
        assert device.auth_key_state == "active"
        assert device.auth_public_key_pem
        assert device.auth_public_key_fingerprint == body["key_fingerprint"]
        # No attestation -> security level is None
        assert device.attestation_security_level is None

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

    def test_register_key_with_enrollment_specific_id(self, client):
        """Registration stores enrollment_specific_id when provided."""
        device = DeviceFactory()
        private_key = self._new_private_key()
        resp = client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "public_key_pem": self._public_pem(private_key),
                    "package_name": "com.publishmdm.agent",
                    "enrollment_specific_id": "esid-12345",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        device.refresh_from_db()
        assert device.enrollment_specific_id == "esid-12345"

    def test_register_key_missing_device_id(self, client):
        resp = client.post(
            self.register_url,
            data=json.dumps(
                {
                    "public_key_pem": "-----BEGIN PUBLIC KEY-----\nfoo\n-----END PUBLIC KEY-----",
                    "package_name": "com.publishmdm.agent",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_register_key_missing_both_key_and_chain(self, client):
        """Registration fails when neither public_key_pem nor certificate_chain is provided."""
        device = DeviceFactory()
        resp = client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "package_name": "com.publishmdm.agent",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_register_key_wrong_package_name(self, client):
        device = DeviceFactory()
        private_key = self._new_private_key()
        resp = client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "public_key_pem": self._public_pem(private_key),
                    "package_name": "com.other.app",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 403

    # -------------------------------------------------------------------------
    # Register key -- attested (certificate chain) with mocked validation
    # -------------------------------------------------------------------------

    def test_register_key_attested_success(self, client):
        """Registration with certificate_chain succeeds when attestation validates."""
        device = DeviceFactory()
        nonce = "a1b2c3d4" * 8  # 64 hex chars

        DeviceAttestationNonce.objects.create(
            device=device,
            nonce=nonce,
            expires_at=now() + timedelta(minutes=10),
        )

        private_key = self._new_private_key()
        public_key_pem = self._public_pem(private_key)

        mock_result = {
            "public_key": private_key.public_key(),
            "public_key_pem": public_key_pem,
            "fingerprint": "deadbeef" * 8,
            "security_level": 1,  # TEE
        }

        with patch("apps.mdm.views.validate_attestation", return_value=mock_result):
            resp = client.post(
                self.register_url,
                data=json.dumps(
                    {
                        "device_id": device.device_id,
                        "certificate_chain": ["cert1_b64", "cert2_b64"],
                        "package_name": "com.publishmdm.agent",
                    }
                ),
                content_type="application/json",
            )

        assert resp.status_code == 201
        device.refresh_from_db()
        assert device.auth_key_state == "active"
        assert device.attestation_security_level == 1
        assert device.auth_public_key_fingerprint == "deadbeef" * 8

        nonce_record = DeviceAttestationNonce.objects.get(nonce=nonce)
        assert nonce_record.used_at is not None

    def test_register_key_attested_invalid_chain(self, client):
        """Registration fails when attestation validation raises an error."""
        device = DeviceFactory()
        nonce = "a1b2c3d4" * 8

        DeviceAttestationNonce.objects.create(
            device=device,
            nonce=nonce,
            expires_at=now() + timedelta(minutes=10),
        )

        with patch(
            "apps.mdm.views.validate_attestation",
            side_effect=AttestationError("Bad chain"),
        ):
            resp = client.post(
                self.register_url,
                data=json.dumps(
                    {
                        "device_id": device.device_id,
                        "certificate_chain": ["cert1_b64", "cert2_b64"],
                        "package_name": "com.publishmdm.agent",
                    }
                ),
                content_type="application/json",
            )

        assert resp.status_code == 401

    def test_register_key_attested_expired_nonce(self, client):
        """Registration fails when all nonces are expired."""
        device = DeviceFactory()
        nonce = "a1b2c3d4" * 8

        DeviceAttestationNonce.objects.create(
            device=device,
            nonce=nonce,
            expires_at=now() - timedelta(minutes=1),
        )

        resp = client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "certificate_chain": ["cert1_b64", "cert2_b64"],
                    "package_name": "com.publishmdm.agent",
                }
            ),
            content_type="application/json",
        )

        assert resp.status_code == 401

    def test_register_key_attested_chain_too_short(self, client):
        """Registration fails when certificate_chain has fewer than 2 entries."""
        device = DeviceFactory()
        resp = client.post(
            self.register_url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "certificate_chain": ["only_one_cert"],
                    "package_name": "com.publishmdm.agent",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400

    # -------------------------------------------------------------------------
    # Challenge and verify flow
    # -------------------------------------------------------------------------

    def test_challenge_and_verify_success(self, client):
        device = DeviceFactory()

        private_key = self._new_private_key()
        register_resp = client.post(
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

        private_key = self._new_private_key()
        client.post(
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

        private_key = self._new_private_key()
        client.post(
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

    def _register_device(self, device):
        private_key = self._new_private_key()
        pem = self._public_pem(private_key)
        der = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        device.auth_public_key_pem = pem
        device.auth_public_key_fingerprint = hashlib.sha256(der).hexdigest()
        device.auth_key_state = "active"
        device.auth_key_version = 1
        device.save(
            update_fields=[
                "auth_public_key_pem",
                "auth_public_key_fingerprint",
                "auth_key_state",
                "auth_key_version",
            ]
        )
        return private_key

    def _sign_request(self, private_key, device_id):
        timestamp = str(int(time.time()))
        payload = f"{device_id}.{timestamp}".encode()
        signature = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return {
            "device_id": device_id,
            "timestamp": timestamp,
            "signature_b64": base64.b64encode(signature).decode("ascii"),
        }

    def test_sync_policy_success(self, client, mocker):
        device = DeviceFactory()
        key = self._register_device(device)
        mock_mdm = mocker.MagicMock()
        mocker.patch(
            "apps.mdm.views.get_active_mdm_instance",
            return_value=mock_mdm,
        )
        body = self._sign_request(key, device.device_id)
        resp = client.post(self.url, data=json.dumps(body), content_type="application/json")
        assert resp.status_code == 204
        mock_mdm.push_device_config.assert_called_once_with(device)

    def test_sync_policy_invalid_signature_returns_401(self, client, mocker):
        device = DeviceFactory()
        self._register_device(device)
        mocker.patch("apps.mdm.views.get_active_mdm_instance", return_value=mocker.MagicMock())
        # Sign with a different key
        wrong_key = self._new_private_key()
        body = self._sign_request(wrong_key, device.device_id)
        resp = client.post(self.url, data=json.dumps(body), content_type="application/json")
        assert resp.status_code == 401

    def test_sync_policy_missing_signature_returns_400(self, client):
        device = DeviceFactory()
        self._register_device(device)
        resp = client.post(
            self.url,
            data=json.dumps({"device_id": device.device_id}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_sync_policy_unregistered_device_returns_401(self, client):
        device = DeviceFactory()
        resp = client.post(
            self.url,
            data=json.dumps(
                {
                    "device_id": device.device_id,
                    "timestamp": str(int(time.time())),
                    "signature_b64": "badsig",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_sync_policy_missing_device_id(self, client):
        resp = client.post(
            self.url,
            data=json.dumps({"timestamp": "123", "signature_b64": "sig"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_sync_policy_empty_body(self, client):
        resp = client.post(self.url, data="", content_type="application/json")
        assert resp.status_code == 400

    def test_sync_policy_by_serial_number(self, client, mocker):
        device = DeviceFactory(serial_number="SN-SYNC-TEST")
        key = self._register_device(device)
        mock_mdm = mocker.MagicMock()
        mocker.patch(
            "apps.mdm.views.get_active_mdm_instance",
            return_value=mock_mdm,
        )
        body = self._sign_request(key, "SN-SYNC-TEST")
        resp = client.post(self.url, data=json.dumps(body), content_type="application/json")
        assert resp.status_code == 204
        mock_mdm.push_device_config.assert_called_once_with(device)

    def test_sync_policy_clock_skew_returns_400_with_server_time(self, client):
        device = DeviceFactory()
        key = self._register_device(device)
        stale_timestamp = str(int(time.time()) - 120)  # 2 minutes old
        payload = f"{device.device_id}.{stale_timestamp}".encode()
        signature = key.sign(payload, ec.ECDSA(hashes.SHA256()))
        body = {
            "device_id": device.device_id,
            "timestamp": stale_timestamp,
            "signature_b64": base64.b64encode(signature).decode("ascii"),
        }
        resp = client.post(self.url, data=json.dumps(body), content_type="application/json")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] == "clock_skew"
        assert isinstance(data["server_time"], int)

    def test_sync_policy_get_not_allowed(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 405
