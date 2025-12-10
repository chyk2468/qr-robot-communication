"""
QR-Link Anti-Replay & Temporal Integrity Guard
Protects against visual recording playback attacks and timestamp drift.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Set, Optional, Tuple


@dataclass
class SecurityCheckResult:
    passed: bool
    signature_valid: bool
    timestamp_fresh: bool
    nonce_unique: bool
    sequence_valid: bool
    time_delta_seconds: float
    error_reasons: list = field(default_factory=list)


class AntiReplayGuard:
    """
    Monitors incoming optical transactions to enforce:
    1. Time freshness window (|T_now - T_msg| <= max_skew)
    2. One-time nonce uniqueness within a TTL cache
    3. Strictly monotonic sequence counters per sender ID
    """

    def __init__(self, max_skew_seconds: float = 10.0, nonce_ttl_seconds: float = 300.0):
        self.max_skew_seconds = max_skew_seconds
        self.nonce_ttl_seconds = nonce_ttl_seconds
        
        # In-memory storage: {nonce: expiration_timestamp}
        self.nonce_cache: Dict[str, float] = {}
        
        # Last observed sequence number per sender: {sender_id: last_seq}
        self.sender_sequence_map: Dict[str, int] = {}

    def cleanup_expired_nonces(self):
        """Purge nonces that have exceeded their TTL."""
        now = time.time()
        expired = [n for n, exp in self.nonce_cache.items() if exp <= now]
        for n in expired:
            del self.nonce_cache[n]

    def verify_message_integrity(
        self,
        sender_id: str,
        sequence_num: int,
        timestamp_iso: str,
        nonce: str,
        signature_valid: bool,
    ) -> SecurityCheckResult:
        """
        Execute full multi-tier temporal and replay verification.
        """
        self.cleanup_expired_nonces()
        errors = []

        # 1. Signature validity check
        if not signature_valid:
            errors.append("Digital signature is invalid or unauthenticated.")

        # 2. Timestamp freshness check
        now_utc = datetime.now(timezone.utc)
        try:
            msg_utc = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
            time_delta = (now_utc - msg_utc).total_seconds()
            timestamp_fresh = abs(time_delta) <= self.max_skew_seconds
            if not timestamp_fresh:
                errors.append(
                    f"Timestamp expired or drifted: delta is {time_delta:.2f}s (max allowed {self.max_skew_seconds}s)."
                )
        except Exception as e:
            timestamp_fresh = False
            time_delta = 9999.0
            errors.append(f"Invalid timestamp ISO formatting: {e}")

        # 3. Nonce uniqueness check
        now_epoch = time.time()
        if nonce in self.nonce_cache:
            nonce_unique = False
            errors.append(f"Replay attack detected: Nonce '{nonce}' has already been processed.")
        else:
            nonce_unique = True
            # Cache nonce with TTL
            self.nonce_cache[nonce] = now_epoch + self.nonce_ttl_seconds

        # 4. Monotonic Sequence Number check
        last_seq = self.sender_sequence_map.get(sender_id, 0)
        if sequence_num <= last_seq:
            sequence_valid = False
            errors.append(
                f"Invalid sequence counter: received #{sequence_num}, expected > #{last_seq} for sender '{sender_id}'."
            )
        else:
            sequence_valid = True
            self.sender_sequence_map[sender_id] = sequence_num

        overall_passed = signature_valid and timestamp_fresh and nonce_unique and sequence_valid

        return SecurityCheckResult(
            passed=overall_passed,
            signature_valid=signature_valid,
            timestamp_fresh=timestamp_fresh,
            nonce_unique=nonce_unique,
            sequence_valid=sequence_valid,
            time_delta_seconds=round(time_delta, 3),
            error_reasons=errors,
        )

    def reset_state(self):
        """Clear all replay caches and sequence tracking."""
        self.nonce_cache.clear()
        self.sender_sequence_map.clear()
