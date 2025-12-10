"""
Unit tests for QR-Link Cryptographic Security & Anti-Replay Guard
"""

import pytest
import time
from datetime import datetime, timezone, timedelta
from security.authentication import (
    CryptoSigner,
    generate_ed25519_keypair,
    sign_canonical_payload,
    verify_payload_signature,
)
from security.anti_replay import AntiReplayGuard


def test_ed25519_keypair_and_signature():
    keypair = generate_ed25519_keypair()
    assert len(keypair.private_key_hex) == 64
    assert len(keypair.public_key_hex) == 64

    payload = {
        "sender_id": "ROBOT_A",
        "command": "NAVIGATE_TO",
        "parameters": {"target_zone": "Z1"},
    }

    sig = sign_canonical_payload(payload, keypair.private_key_hex)
    assert len(sig) == 128  # 64 bytes in hex

    # Positive verification
    is_valid = verify_payload_signature(payload, sig, keypair.public_key_hex)
    assert is_valid is True


def test_ed25519_tamper_rejection():
    keypair = generate_ed25519_keypair()
    payload = {"sender": "ROBOT_A", "speed": 0.5}
    sig = sign_canonical_payload(payload, keypair.private_key_hex)

    # Tamper payload
    tampered_payload = {"sender": "ROBOT_A", "speed": 10.0}
    is_valid = verify_payload_signature(tampered_payload, sig, keypair.public_key_hex)
    assert is_valid is False


def test_anti_replay_freshness_and_nonce():
    guard = AntiReplayGuard(max_skew_seconds=5.0, nonce_ttl_seconds=60.0)

    now_iso = datetime.now(timezone.utc).isoformat()
    nonce1 = "nonce_abc_123"

    # 1. Normal valid packet
    res1 = guard.verify_message_integrity(
        sender_id="ROBOT_A",
        sequence_num=1,
        timestamp_iso=now_iso,
        nonce=nonce1,
        signature_valid=True,
    )
    assert res1.passed is True
    assert res1.nonce_unique is True
    assert res1.sequence_valid is True

    # 2. Replay attack with same nonce
    res2 = guard.verify_message_integrity(
        sender_id="ROBOT_A",
        sequence_num=2,
        timestamp_iso=now_iso,
        nonce=nonce1,
        signature_valid=True,
    )
    assert res2.passed is False
    assert res2.nonce_unique is False
    assert "Replay attack detected" in res2.error_reasons[0]


def test_anti_replay_expired_timestamp():
    guard = AntiReplayGuard(max_skew_seconds=5.0)
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()

    res = guard.verify_message_integrity(
        sender_id="ROBOT_A",
        sequence_num=10,
        timestamp_iso=old_time,
        nonce="nonce_unique_99",
        signature_valid=True,
    )
    assert res.passed is False
    assert res.timestamp_fresh is False
