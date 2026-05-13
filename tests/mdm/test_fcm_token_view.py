import base64
import hashlib
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from tests.mdm.factories import DeviceFactory


def _register_key(device):
    """Register an ECDSA key on a device and return the private key."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
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


def _sign_request(private_key, device_id):
    """Sign a request payload and return the auth fields dict."""
    timestamp = str(int(time.time()))
    payload = f"{device_id}.{timestamp}".encode()
    signature = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
    return {
        "device_id": device_id,
        "timestamp": timestamp,
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }


@pytest.mark.django_db
class TestDeviceFcmTokenView:
    """Tests for the device_fcm_token_view endpoint."""

    url = "/mdm/api/devices/fcm-token/"

    def test_register_fcm_token(self, client):
        device = DeviceFactory()
        key = _register_key(device)
        body = {**_sign_request(key, device.device_id), "fcm_token": "new-fcm-token"}
        resp = client.post(self.url, data=json.dumps(body), content_type="application/json")
        assert resp.status_code == 204
        device.refresh_from_db()
        assert device.fcm_token == "new-fcm-token"

    def test_updates_existing_token(self, client):
        device = DeviceFactory(fcm_token="old-token")
        key = _register_key(device)
        body = {**_sign_request(key, device.device_id), "fcm_token": "updated-token"}
        resp = client.post(self.url, data=json.dumps(body), content_type="application/json")
        assert resp.status_code == 204
        device.refresh_from_db()
        assert device.fcm_token == "updated-token"

    def test_unregistered_device_returns_401(self, client):
        device = DeviceFactory()
        resp = client.post(
            self.url,
            data=json.dumps(
                {
                    "fcm_token": "tok",
                    "device_id": device.device_id,
                    "timestamp": str(int(time.time())),
                    "signature_b64": "badsig",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_missing_fcm_token_returns_400(self, client):
        device = DeviceFactory()
        key = _register_key(device)
        body = _sign_request(key, device.device_id)
        resp = client.post(self.url, data=json.dumps(body), content_type="application/json")
        assert resp.status_code == 400

    def test_missing_signature_returns_400(self, client):
        resp = client.post(
            self.url,
            data=json.dumps({"fcm_token": "tok", "device_id": "some-id"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_oversized_fcm_token_returns_400(self, client):
        device = DeviceFactory()
        key = _register_key(device)
        body = {**_sign_request(key, device.device_id), "fcm_token": "x" * 257}
        resp = client.post(self.url, data=json.dumps(body), content_type="application/json")
        assert resp.status_code == 400

    def test_empty_body_returns_400(self, client):
        resp = client.post(self.url, data="", content_type="application/json")
        assert resp.status_code == 400

    def test_invalid_json_returns_400(self, client):
        resp = client.post(self.url, data="not json", content_type="application/json")
        assert resp.status_code == 400

    def test_clock_skew_returns_400_with_server_time(self, client):
        device = DeviceFactory()
        key = _register_key(device)
        stale_timestamp = str(int(time.time()) - 120)  # 2 minutes old
        payload = f"{device.device_id}.{stale_timestamp}".encode()
        signature = key.sign(payload, ec.ECDSA(hashes.SHA256()))
        body = {
            "device_id": device.device_id,
            "timestamp": stale_timestamp,
            "signature_b64": base64.b64encode(signature).decode("ascii"),
            "fcm_token": "tok",
        }
        resp = client.post(self.url, data=json.dumps(body), content_type="application/json")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] == "clock_skew"
        assert isinstance(data["server_time"], int)

    def test_get_not_allowed(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 405
