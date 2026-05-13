"""Android Key Attestation certificate chain validation.

Validates that a device-generated key pair is backed by genuine Android
hardware (TEE/StrongBox) by verifying the X.509 certificate chain roots
in a Google Hardware Attestation Root CA and parsing the attestation
extension (OID 1.3.6.1.4.1.11129.2.1.17).

References:
  - https://developer.android.com/privacy-and-security/security-key-attestation
  - https://developer.android.com/reference/android/security/keystore/KeyGenParameterSpec
"""

import base64
import hashlib
import logging

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_der_public_key
from cryptography.x509.oid import ObjectIdentifier
from OpenSSL.crypto import (
    FILETYPE_ASN1,
    X509Store,
    X509StoreContext,
    X509StoreContextError,
    dump_publickey,
    load_certificate,
)
from pyasn1.codec.ber import decoder as ber_decoder
from pyasn1.codec.der import decoder as asn1_decoder
from pyasn1.type import univ
from pyasn1_modules import rfc5280

logger = logging.getLogger(__name__)

# OID for Android Key Attestation extension
_ATTESTATION_EXTENSION_OID_STR = "1.3.6.1.4.1.11129.2.1.17"
ATTESTATION_EXTENSION_OID = ObjectIdentifier(_ATTESTATION_EXTENSION_OID_STR)

# Google Hardware Attestation Root CA certificates (PEM).
# Downloaded from https://android.googleapis.com/attestation/root
#
# Root 0: RSA (serial f92009e853b6b045)
# Root 1: ECDSA P-384 (2026+ devices with Remote Key Provisioning)
GOOGLE_ROOT_RSA_PEM = """\
-----BEGIN CERTIFICATE-----
MIIFHDCCAwSgAwIBAgIJAPHBcqaZ6vUdMA0GCSqGSIb3DQEBCwUAMBsxGTAXBgNV
BAUTEGY5MjAwOWU4NTNiNmIwNDUwHhcNMjIwMzIwMTgwNzQ4WhcNNDIwMzE1MTgw
NzQ4WjAbMRkwFwYDVQQFExBmOTIwMDllODUzYjZiMDQ1MIICIjANBgkqhkiG9w0B
AQEFAAOCAg8AMIICCgKCAgEAr7bHgiuxpwHsK7Qui8xUFmOr75gvMsd/dTEDDJdS
Sxtf6An7xyqpRR90PL2abxM1dEqlXnf2tqw1Ne4Xwl5jlRfdnJLmN0pTy/4lj4/7
tv0Sk3iiKkypnEUtR6WfMgH0QZfKHM1+di+y9TFRtv6y//0rb+T+W8a9nsNL/ggj
nar86461qO0rOs2cXjp3kOG1FEJ5MVmFmBGtnrKpa73XpXyTqRxB/M0n1n/W9nGq
C4FSYa04T6N5RIZGBN2z2MT5IKGbFlbC8UrW0DxW7AYImQQcHtGl/m00QLVWutHQ
oVJYnFPlXTcHYvASLu+RhhsbDmxMgJJ0mcDpvsC4PjvB+TxywElgS70vE0XmLD+O
JtvsBslHZvPBKCOdT0MS+tgSOIfga+z1Z1g7+DVagf7quvmag8jfPioyKvxnK/Eg
sTUVi2ghzq8wm27ud/mIM7AY2qEORR8Go3TVB4HzWQgpZrt3i5MIlCaY504LzSRi
igHCzAPlHws+W0rB5N+er5/2pJKnfBSDiCiFAVtCLOZ7gLiMm0jhO2B6tUXHI/+M
RPjy02i59lINMRRev56GKtcd9qO/0kUJWdZTdA2XoS82ixPvZtXQpUpuL12ab+9E
aDK8Z4RHJYYfCT3Q5vNAXaiWQ+8PTWm2QgBR/bkwSWc+NpUFgNPN9PvQi8WEg5Um
AGMCAwEAAaNjMGEwHQYDVR0OBBYEFDZh4QB8iAUJUYtEbEf/GkzJ6k8SMB8GA1Ud
IwQYMBaAFDZh4QB8iAUJUYtEbEf/GkzJ6k8SMA8GA1UdEwEB/wQFMAMBAf8wDgYD
VR0PAQH/BAQDAgIEMA0GCSqGSIb3DQEBCwUAA4ICAQB8cMqTllHc8U+qCrOlg3H7
174lmaCsbo/bJ0C17JEgMLb4kvrqsXZs01U3mB/qABg/1t5Pd5AORHARs1hhqGIC
W/nKMav574f9rZN4PC2ZlufGXb7sIdJpGiO9ctRhiLuYuly10JccUZGEHpHSYM2G
tkgYbZba6lsCPYAAP83cyDV+1aOkTf1RCp/lM0PKvmxYN10RYsK631jrleGdcdkx
oSK//mSQbgcWnmAEZrzHoF1/0gso1HZgIn0YLzVhLSA/iXCX4QT2h3J5z3znluKG
1nv8NQdxei2DIIhASWfu804CA96cQKTTlaae2fweqXjdN1/v2nqOhngNyz1361mF
mr4XmaKH/ItTwOe72NI9ZcwS1lVaCvsIkTDCEXdm9rCNPAY10iTunIHFXRh+7KPz
lHGewCq/8TOohBRn0/NNfh7uRslOSZ/xKbN9tMBtw37Z8d2vvnXq/YWdsm1+JLVw
n6yYD/yacNJBlwpddla8eaVMjsF6nBnIgQOf9zKSe06nSTqvgwUHosgOECZJZ1Eu
zbH4yswbt02tKtKEFhx+v+OTge/06V+jGsqTWLsfrOCNLuA8H++z+pUENmpqnnHo
vaI47gC+TNpkgYGkkBT6B/m/U01BuOBBTzhIlMEZq9qkDWuM2cA5kW5V3FJUcfHn
w1IdYIg2Wxg7yHcQZemFQg==
-----END CERTIFICATE-----"""

# ECDSA P-384 root (2026+ devices with Remote Key Provisioning v2)
GOOGLE_ROOT_EC_P384_PEM = """\
-----BEGIN CERTIFICATE-----
MIICIjCCAaigAwIBAgIRAISp0Cl7DrWK5/8OgN52BgUwCgYIKoZIzj0EAwMwUjEc
MBoGA1UEAwwTS2V5IEF0dGVzdGF0aW9uIENBMTEQMA4GA1UECwwHQW5kcm9pZDET
MBEGA1UECgwKR29vZ2xlIExMQzELMAkGA1UEBhMCVVMwHhcNMjUwNzE3MjIzMjE4
WhcNMzUwNzE1MjIzMjE4WjBSMRwwGgYDVQQDDBNLZXkgQXR0ZXN0YXRpb24gQ0Ex
MRAwDgYDVQQLDAdBbmRyb2lkMRMwEQYDVQQKDApHb29nbGUgTExDMQswCQYDVQQG
EwJVUzB2MBAGByqGSM49AgEGBSuBBAAiA2IABCPaI3FO3z5bBQo8cuiEas4HjqCt
G/mLFfRT0MsIssPBEEU5Cfbt6sH5yOAxqEi5QagpU1yX4HwnGb7OtBYpDTB57uH5
Eczm34A5FNijV3s0/f0UPl7zbJcTx6xwqMIRq6NCMEAwDwYDVR0TAQH/BAUwAwEB
/zAOBgNVHQ8BAf8EBAMCAQYwHQYDVR0OBBYEFFIyuyz7RkOb3NaBqQ5lZuA0QepA
MAoGCCqGSM49BAMDA2gAMGUCMETfjPO/HwqReR2CS7p0ZWoD/LHs6hDi422opifH
EUaYLxwGlT9SLdjkVpz0UUOR5wIxAIoGyxGKRHVTpqpGRFiJtQEOOTp/+s1GcxeY
uR2zh/80lQyu9vAFCj6E4AXc+osmRg==
-----END CERTIFICATE-----"""


def _load_trusted_roots():
    """Load the set of trusted Google Hardware Attestation Root CA certificates."""
    roots = []
    for pem in (GOOGLE_ROOT_RSA_PEM, GOOGLE_ROOT_EC_P384_PEM):
        roots.append(x509.load_pem_x509_certificate(pem.encode()))
    return roots


TRUSTED_ROOTS = _load_trusted_roots()
_TRUSTED_ROOT_FINGERPRINTS = {
    hashlib.sha256(
        root.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).hexdigest()
    for root in TRUSTED_ROOTS
}


class AttestationError(Exception):
    """Raised when attestation validation fails."""

    pass


def decode_certificate_chain(encoded_certs: list[str]) -> list[bytes]:
    """Decode a list of Base64-encoded DER certificates into raw DER bytes.

    Returns a list of DER bytes (leaf first, root last).

    Uses pyOpenSSL to validate each certificate is parseable — pyOpenSSL uses
    the OpenSSL C library which is lenient about BER non-conformances in
    Android-generated attestation certificates (e.g., extensions with
    ``critical = FALSE`` explicitly encoded rather than omitted).
    """
    cert_ders = []
    for i, b64 in enumerate(encoded_certs):
        try:
            der_bytes = base64.b64decode(b64)
            load_certificate(FILETYPE_ASN1, der_bytes)  # validate parseability
            cert_ders.append(der_bytes)
        except Exception as e:
            raise AttestationError(f"Invalid certificate at index {i}: {e}") from e
    return cert_ders


def verify_certificate_chain(cert_ders: list[bytes]) -> None:
    """Verify that the certificate chain is valid and roots in a Google CA.

    Uses pyOpenSSL (OpenSSL C library) for chain signature verification so
    that Android-generated certificates with BER non-conformances (e.g.,
    ``critical = FALSE`` explicitly encoded) are accepted.

    Args:
        cert_ders: List of DER-encoded certificates, leaf first, root last.

    Raises:
        AttestationError: If the chain is invalid.
    """
    if len(cert_ders) < 2:
        raise AttestationError("Certificate chain must have at least 2 certificates (leaf + root)")

    # Verify the root is a trusted Google root
    root_ossl = load_certificate(FILETYPE_ASN1, cert_ders[-1])
    root_pubkey_der = dump_publickey(FILETYPE_ASN1, root_ossl.get_pubkey())
    root_fingerprint = hashlib.sha256(root_pubkey_der).hexdigest()
    if root_fingerprint not in _TRUSTED_ROOT_FINGERPRINTS:
        logger.warning(
            "Root certificate not trusted: fingerprint=%s chain_len=%d",
            root_fingerprint,
            len(cert_ders),
        )
        raise AttestationError("Root certificate is not a trusted Google Hardware Attestation Root")

    # Build an OpenSSL trust store containing root + intermediates, then
    # verify the leaf.  OpenSSL's C implementation tolerates BER encoding
    # quirks that cryptography's strict Rust parser rejects.
    store = X509Store()
    for der in cert_ders[1:]:
        store.add_cert(load_certificate(FILETYPE_ASN1, der))

    leaf_ossl = load_certificate(FILETYPE_ASN1, cert_ders[0])
    ctx = X509StoreContext(store, leaf_ossl)
    try:
        ctx.verify_certificate()
    except X509StoreContextError as e:
        raise AttestationError(f"Certificate chain verification failed: {e}") from e


def _get_extension_value(cert_der: bytes, oid_str: str) -> bytes | None:
    """Extract extension ``extnValue`` bytes from certificate DER.

    Uses pyasn1 BER decoder (lenient) rather than the cryptography library
    so that certs with BER non-conformances are accepted.

    Args:
        cert_der: Raw DER bytes of the certificate.
        oid_str: The dotted-string OID of the extension to look for.

    Returns:
        The raw bytes of the extension's ``extnValue`` OCTET STRING, or
        ``None`` if the extension is not present.
    """
    try:
        cert, _ = ber_decoder.decode(cert_der, asn1Spec=rfc5280.Certificate())
        for ext in cert["tbsCertificate"]["extensions"]:
            if str(ext["extnID"]) == oid_str:
                return bytes(ext["extnValue"])
    except Exception:
        pass
    return None


def extract_attestation_challenge(leaf_der: bytes) -> bytes:
    """Extract the attestation challenge from the leaf certificate DER.

    The attestation extension has OID 1.3.6.1.4.1.11129.2.1.17 and contains an ASN.1
    SEQUENCE where the attestationChallenge is at index 4.

    Args:
        leaf_der: Raw DER bytes of the leaf (device key) certificate.

    Returns:
        The attestation challenge bytes.

    Raises:
        AttestationError: If the extension is missing or cannot be parsed.
    """
    ext_value = _get_extension_value(leaf_der, _ATTESTATION_EXTENSION_OID_STR)
    if ext_value is None:
        raise AttestationError("Leaf certificate missing attestation extension")
    try:
        attestation_seq, _ = asn1_decoder.decode(ext_value, asn1Spec=univ.Sequence())
        # attestationChallenge is at index 4 in the KeyDescription SEQUENCE
        challenge_asn1 = attestation_seq.getComponentByPosition(4)
        return bytes(challenge_asn1)
    except Exception as e:
        raise AttestationError(f"Failed to parse attestation extension: {e}") from e


def extract_security_level(leaf_der: bytes) -> int:
    """Extract the attestation security level from the leaf certificate DER.

    Security levels:
        0 = Software
        1 = TrustedEnvironment (TEE)
        2 = StrongBox

    Args:
        leaf_der: Raw DER bytes of the leaf (device key) certificate.

    Returns:
        The security level integer.

    Raises:
        AttestationError: If the extension is missing or cannot be parsed.
    """
    ext_value = _get_extension_value(leaf_der, _ATTESTATION_EXTENSION_OID_STR)
    if ext_value is None:
        raise AttestationError("Leaf certificate missing attestation extension")
    try:
        attestation_seq, _ = asn1_decoder.decode(ext_value, asn1Spec=univ.Sequence())
        # attestationSecurityLevel is at index 1 in the KeyDescription SEQUENCE
        security_level = int(attestation_seq.getComponentByPosition(1))
        return security_level
    except Exception as e:
        raise AttestationError(f"Failed to parse security level: {e}") from e


def extract_public_key(leaf_der: bytes) -> ec.EllipticCurvePublicKey:
    """Extract the EC public key from the leaf certificate DER.

    Uses pyOpenSSL + cryptography to support certificates with BER
    non-conformances.

    Args:
        leaf_der: Raw DER bytes of the leaf (device key) certificate.

    Raises:
        AttestationError: If the key is not an EC key or extraction fails.
    """
    try:
        ossl_cert = load_certificate(FILETYPE_ASN1, leaf_der)
        pubkey_der = dump_publickey(FILETYPE_ASN1, ossl_cert.get_pubkey())
        key = load_der_public_key(pubkey_der)
    except Exception as e:
        raise AttestationError(f"Failed to extract public key: {e}") from e

    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise AttestationError(f"Expected EC public key, got {type(key).__name__}")
    return key


def validate_attestation(
    encoded_certs: list[str],
    expected_nonce: bytes,
    require_hardware: bool = True,
) -> dict:
    """Full attestation validation pipeline.

    Args:
        encoded_certs: Base64-encoded DER certificates (leaf first, root last).
        expected_nonce: The nonce that was issued by the server.
        require_hardware: If True, reject Software security level.

    Returns:
        dict with keys:
            - public_key: EC public key object
            - public_key_pem: PEM-encoded public key string
            - fingerprint: SHA-256 hex fingerprint of the DER-encoded public key
            - security_level: int (0=Software, 1=TEE, 2=StrongBox)

    Raises:
        AttestationError: If validation fails.
    """
    cert_ders = decode_certificate_chain(encoded_certs)
    if not cert_ders:
        raise AttestationError("Empty certificate chain")

    verify_certificate_chain(cert_ders)

    leaf_der = cert_ders[0]

    # Verify the nonce matches
    challenge = extract_attestation_challenge(leaf_der)
    if challenge != expected_nonce:
        raise AttestationError("Attestation challenge does not match server nonce")

    # Check security level
    security_level = extract_security_level(leaf_der)
    if require_hardware and security_level == 0:
        raise AttestationError(
            "Hardware-backed attestation required but got Software security level. "
            "This may indicate an emulator or rooted device."
        )

    # Extract the public key
    public_key = extract_public_key(leaf_der)
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    public_key_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    fingerprint = hashlib.sha256(public_key_der).hexdigest()

    return {
        "public_key": public_key,
        "public_key_pem": public_key_pem,
        "fingerprint": fingerprint,
        "security_level": security_level,
    }
