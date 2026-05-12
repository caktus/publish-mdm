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
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509.oid import ObjectIdentifier
from pyasn1.codec.der import decoder as asn1_decoder
from pyasn1.type import univ

logger = logging.getLogger(__name__)

# OID for Android Key Attestation extension
ATTESTATION_EXTENSION_OID = ObjectIdentifier("1.3.6.1.4.1.11129.2.1.17")

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


def decode_certificate_chain(encoded_certs: list[str]) -> list[x509.Certificate]:
    """Decode a list of Base64-encoded DER certificates into x509.Certificate objects."""
    certs = []
    for i, b64 in enumerate(encoded_certs):
        try:
            der_bytes = base64.b64decode(b64)
            certs.append(x509.load_der_x509_certificate(der_bytes))
        except Exception as e:
            raise AttestationError(f"Invalid certificate at index {i}: {e}") from e
    return certs


def verify_certificate_chain(certs: list[x509.Certificate]) -> None:
    """Verify that the certificate chain is valid and roots in a Google CA.

    Args:
        certs: List of certificates, leaf first, root last.

    Raises:
        AttestationError: If the chain is invalid.
    """
    if len(certs) < 2:
        raise AttestationError("Certificate chain must have at least 2 certificates (leaf + root)")

    # Verify the root is a trusted Google root
    root = certs[-1]
    root_fingerprint = hashlib.sha256(
        root.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).hexdigest()
    if root_fingerprint not in _TRUSTED_ROOT_FINGERPRINTS:
        logger.warning(
            "Root certificate not trusted",
            root_subject=str(root.subject),
            root_fingerprint=root_fingerprint,
            chain_len=len(certs),
        )
        raise AttestationError("Root certificate is not a trusted Google Hardware Attestation Root")

    # Walk the chain from root to leaf, verifying each link
    for i in range(len(certs) - 1, 0, -1):
        issuer = certs[i]
        subject = certs[i - 1]
        _verify_cert_signature(subject, issuer)


def _verify_cert_signature(subject: x509.Certificate, issuer: x509.Certificate) -> None:
    """Verify that issuer signed subject's certificate."""
    issuer_public_key = issuer.public_key()
    try:
        if isinstance(issuer_public_key, rsa.RSAPublicKey):
            issuer_public_key.verify(
                subject.signature,
                subject.tbs_certificate_bytes,
                padding.PKCS1v15(),
                subject.signature_hash_algorithm,
            )
        elif isinstance(issuer_public_key, ec.EllipticCurvePublicKey):
            issuer_public_key.verify(
                subject.signature,
                subject.tbs_certificate_bytes,
                ec.ECDSA(subject.signature_hash_algorithm),
            )
        else:
            raise AttestationError(f"Unsupported key type: {type(issuer_public_key).__name__}")
    except InvalidSignature as err:
        raise AttestationError(
            f"Certificate signature verification failed: "
            f"{subject.subject} not signed by {issuer.subject}"
        ) from err


def extract_attestation_challenge(leaf_cert: x509.Certificate) -> bytes:
    """Extract the attestation challenge from the leaf certificate's attestation extension.

    The attestation extension has OID 1.3.6.1.4.1.11129.2.1.17 and contains an ASN.1
    SEQUENCE where the attestationChallenge is at index 4.

    Returns:
        The attestation challenge bytes.

    Raises:
        AttestationError: If the extension is missing or cannot be parsed.
    """
    try:
        ext = leaf_cert.extensions.get_extension_for_oid(ATTESTATION_EXTENSION_OID)
    except x509.ExtensionNotFound:
        raise AttestationError("Leaf certificate missing attestation extension") from None

    ext_value = ext.value.value  # raw DER bytes of the extension value
    try:
        attestation_seq, _ = asn1_decoder.decode(ext_value, asn1Spec=univ.Sequence())
        # attestationChallenge is at index 4 in the KeyDescription SEQUENCE
        challenge_asn1 = attestation_seq.getComponentByPosition(4)
        return bytes(challenge_asn1)
    except Exception as e:
        raise AttestationError(f"Failed to parse attestation extension: {e}") from e


def extract_security_level(leaf_cert: x509.Certificate) -> int:
    """Extract the attestation security level from the leaf certificate.

    Security levels:
        0 = Software
        1 = TrustedEnvironment (TEE)
        2 = StrongBox

    Returns:
        The security level integer.

    Raises:
        AttestationError: If the extension is missing or cannot be parsed.
    """
    try:
        ext = leaf_cert.extensions.get_extension_for_oid(ATTESTATION_EXTENSION_OID)
    except x509.ExtensionNotFound:
        raise AttestationError("Leaf certificate missing attestation extension") from None

    ext_value = ext.value.value
    try:
        attestation_seq, _ = asn1_decoder.decode(ext_value, asn1Spec=univ.Sequence())
        # attestationSecurityLevel is at index 1 in the KeyDescription SEQUENCE
        security_level = int(attestation_seq.getComponentByPosition(1))
        return security_level
    except Exception as e:
        raise AttestationError(f"Failed to parse security level: {e}") from e


def extract_public_key(leaf_cert: x509.Certificate) -> ec.EllipticCurvePublicKey:
    """Extract the EC public key from the leaf certificate.

    Raises:
        AttestationError: If the key is not an EC key.
    """
    key = leaf_cert.public_key()
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
    certs = decode_certificate_chain(encoded_certs)
    if not certs:
        raise AttestationError("Empty certificate chain")

    verify_certificate_chain(certs)

    leaf = certs[0]

    # Verify the nonce matches
    challenge = extract_attestation_challenge(leaf)
    if challenge != expected_nonce:
        raise AttestationError("Attestation challenge does not match server nonce")

    # Check security level
    security_level = extract_security_level(leaf)
    if require_hardware and security_level == 0:
        raise AttestationError(
            "Hardware-backed attestation required but got Software security level. "
            "This may indicate an emulator or rooted device."
        )

    # Extract the public key
    public_key = extract_public_key(leaf)
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
