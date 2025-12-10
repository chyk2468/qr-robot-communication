"""
QR-Link Cryptographic Authentication Module
Provides asymmetric digital signatures using Ed25519 for high-speed,
compact, and tamper-evident optical verification.
"""

import json
from dataclasses import dataclass
from typing import Tuple, Dict, Any, Optional
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature


@dataclass
class KeyPairHex:
    private_key_hex: str
    public_key_hex: str


class CryptoSigner:
    """
    Handles Ed25519 key generation, canonical payload serialization,
    and cryptographic digital signing and verification.
    """

    @staticmethod
    def generate_keypair() -> KeyPairHex:
        """Generate a new Ed25519 private/public keypair in hex format."""
        priv_key = ed25519.Ed25519PrivateKey.generate()
        pub_key = priv_key.public_key()

        priv_bytes = priv_key.private_bytes_raw()
        pub_bytes = pub_key.public_bytes_raw()

        return KeyPairHex(
            private_key_hex=priv_bytes.hex(),
            public_key_hex=pub_bytes.hex(),
        )

    @staticmethod
    def canonical_bytes(payload_dict: Dict[str, Any]) -> bytes:
        """
        Normalize dictionary into deterministic JSON bytes (sorted keys, no spaces)
        excluding existing signature field to prevent circular verification errors.
        """
        clean_dict = json.loads(json.dumps(payload_dict))
        if "security" in clean_dict and isinstance(clean_dict["security"], dict):
            clean_dict["security"].pop("signature", None)

        canonical_str = json.dumps(clean_dict, sort_keys=True, separators=(",", ":"))
        return canonical_str.encode("utf-8")

    @classmethod
    def sign_payload(cls, payload_dict: Dict[str, Any], private_key_hex: str) -> str:
        """
        Compute Ed25519 digital signature over canonical payload bytes.
        """
        priv_bytes = bytes.fromhex(private_key_hex)
        priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)

        message_bytes = cls.canonical_bytes(payload_dict)
        signature_bytes = priv_key.sign(message_bytes)
        return signature_bytes.hex()

    @classmethod
    def verify_signature(
        cls,
        payload_dict: Dict[str, Any],
        signature_hex: str,
        public_key_hex: str,
    ) -> bool:
        """
        Verify Ed25519 digital signature against provided public key.
        """
        if not signature_hex or not public_key_hex:
            return False

        try:
            pub_bytes = bytes.fromhex(public_key_hex)
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            sig_bytes = bytes.fromhex(signature_hex)

            message_bytes = cls.canonical_bytes(payload_dict)
            pub_key.verify(sig_bytes, message_bytes)
            return True
        except (InvalidSignature, ValueError, Exception):
            return False


def generate_ed25519_keypair() -> KeyPairHex:
    return CryptoSigner.generate_keypair()


def sign_canonical_payload(payload_dict: Dict[str, Any], private_key_hex: str) -> str:
    return CryptoSigner.sign_payload(payload_dict, private_key_hex)


def verify_payload_signature(payload_dict: Dict[str, Any], signature_hex: str, public_key_hex: str) -> bool:
    return CryptoSigner.verify_signature(payload_dict, signature_hex, public_key_hex)
