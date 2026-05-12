"""Unit tests for apps.mdm.attestation module."""

import base64
import datetime
import hashlib

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from apps.mdm.attestation import (
    _TRUSTED_ROOT_FINGERPRINTS,
    TRUSTED_ROOTS,
    AttestationError,
    decode_certificate_chain,
    extract_public_key,
    verify_certificate_chain,
)


class TestTrustedRoots:
    def test_two_roots_loaded(self):
        """Both Google root CAs (RSA + P-384) should be loaded."""
        assert len(TRUSTED_ROOTS) == 2

    def test_fingerprints_match_roots(self):
        """Each root certificate's fingerprint should be in the trusted set."""
        for root in TRUSTED_ROOTS:
            der = root.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            fp = hashlib.sha256(der).hexdigest()
            assert fp in _TRUSTED_ROOT_FINGERPRINTS


class TestDecodeCertificateChain:
    def test_decode_valid_cert(self):
        """Decoding a valid self-signed cert succeeds."""
        key = ec.generate_private_key(ec.SECP256R1())
        cert = _self_signed_cert(key)
        b64 = base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()
        result = decode_certificate_chain([b64])
        assert len(result) == 1
        assert isinstance(result[0], x509.Certificate)

    def test_decode_invalid_base64(self):
        with pytest.raises(AttestationError, match="Invalid certificate"):
            decode_certificate_chain(["not-valid-base64!!!"])

    def test_decode_empty_list(self):
        result = decode_certificate_chain([])
        assert result == []


class TestVerifyCertificateChain:
    def test_rejects_chain_with_one_cert(self):
        key = ec.generate_private_key(ec.SECP256R1())
        cert = _self_signed_cert(key)
        with pytest.raises(AttestationError, match="at least 2 certificates"):
            verify_certificate_chain([cert])

    def test_rejects_untrusted_root(self):
        """A chain not rooting in a Google CA is rejected."""
        root_key = ec.generate_private_key(ec.SECP256R1())
        root_cert = _self_signed_cert(root_key, cn="Fake Root")
        leaf_key = ec.generate_private_key(ec.SECP256R1())
        leaf_cert = _issued_cert(leaf_key, root_key, root_cert)
        with pytest.raises(AttestationError, match="not a trusted Google"):
            verify_certificate_chain([leaf_cert, root_cert])


class TestExtractPublicKey:
    def test_extracts_ec_key(self):
        key = ec.generate_private_key(ec.SECP256R1())
        cert = _self_signed_cert(key)
        pub = extract_public_key(cert)
        assert isinstance(pub, ec.EllipticCurvePublicKey)


# ---- helpers ----


def _self_signed_cert(private_key, cn="Test"):
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365))
        .sign(private_key, hashes.SHA256())
    )


def _issued_cert(subject_key, issuer_key, issuer_cert):
    return (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "Leaf")]))
        .issuer_name(issuer_cert.subject)
        .public_key(subject_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365))
        .sign(issuer_key, hashes.SHA256())
    )
