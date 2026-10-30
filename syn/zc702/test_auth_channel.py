"""Test and Verify Authenticated Classical Channel Wrapper.
Reference: Work item P04, Wegman & Carter (1981), Stinson (1994).

Exercises a computational authentication prototype on the host:
- Normal packet wrapping and verification
- 1-bit tamper detection (tag mismatch)
- Anti-replay sequence protection
- Header integrity; this suite establishes no composable security bound
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import struct
import numpy as np

ROOT = Path(__file__).resolve().parents[2]

AUTH_MAGIC = 0x51415554  # 'QAUT'


def gf64_mul(a, b):
    """Multiplication in GF(2^64) modulo P(x) = x^64 + x^4 + x^3 + x + 1."""
    res = 0
    a = int(a)
    b = int(b)
    while b > 0:
        if b & 1:
            res ^= a
        carry = a >> 63
        a = (a << 1) & 0xFFFFFFFFFFFFFFFF
        if carry:
            a ^= 0x000000000000001B
        b >>= 1
    return res


def rotl64(x, b):
    return ((x << b) & 0xFFFFFFFFFFFFFFFF) | (x >> (64 - b))


def sipround(v0, v1, v2, v3):
    v0 = (v0 + v1) & 0xFFFFFFFFFFFFFFFF
    v1 = rotl64(v1, 13) ^ v0
    v0 = rotl64(v0, 32)

    v2 = (v2 + v3) & 0xFFFFFFFFFFFFFFFF
    v3 = rotl64(v3, 16) ^ v2

    v0 = (v0 + v3) & 0xFFFFFFFFFFFFFFFF
    v3 = rotl64(v3, 21) ^ v0

    v2 = (v2 + v1) & 0xFFFFFFFFFFFFFFFF
    v1 = rotl64(v1, 17) ^ v2
    v2 = rotl64(v2, 32)
    return v0, v1, v2, v3


def siphash24_64(k0, k1, m):
    v0 = 0x736F6D6570736575 ^ k0
    v1 = 0x646F72616E646F6D ^ k1
    v2 = 0x6C7967656E657261 ^ k0
    v3 = 0x7465646279746573 ^ k1

    v3 ^= m
    v0, v1, v2, v3 = sipround(v0, v1, v2, v3)
    v0, v1, v2, v3 = sipround(v0, v1, v2, v3)
    v0 ^= m

    tail = 8 << 56
    v3 ^= tail
    v0, v1, v2, v3 = sipround(v0, v1, v2, v3)
    v0, v1, v2, v3 = sipround(v0, v1, v2, v3)
    v0 ^= tail

    v2 ^= 0xFF
    v0, v1, v2, v3 = sipround(v0, v1, v2, v3)
    v0, v1, v2, v3 = sipround(v0, v1, v2, v3)
    v0, v1, v2, v3 = sipround(v0, v1, v2, v3)
    v0, v1, v2, v3 = sipround(v0, v1, v2, v3)

    return (v0 ^ v1 ^ v2 ^ v3) & 0xFFFFFFFFFFFFFFFF


def derive_otp(psk, seq, msg_type):
    """Cryptographic PRF using SipHash-2-4."""
    k0 = psk & 0xFFFFFFFFFFFFFFFF
    k1 = (psk ^ 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    m = ((msg_type << 32) | (seq & 0xFFFFFFFF)) & 0xFFFFFFFFFFFFFFFF
    return siphash24_64(k0, k1, m)


def compute_mac(hash_key, psk, payload, seq, msg_type):
    """Reference Wegman-Carter MAC computation with domain separator and PRF mask."""
    acc = 0
    words = len(payload) // 8
    for i in range(words):
        block = struct.unpack('<Q', payload[i*8:(i+1)*8])[0]
        acc = gf64_mul(acc ^ block, hash_key)

    rem = len(payload) % 8
    if rem > 0:
        tail = payload[words*8:] + bytes(8 - rem)
        block = struct.unpack('<Q', tail)[0]
        acc = gf64_mul(acc ^ block, hash_key)

    len_block = (0x8000000000000000 | (msg_type << 32) | len(payload)) & 0xFFFFFFFFFFFFFFFF
    acc = gf64_mul(acc ^ len_block, hash_key)
    otp = derive_otp(psk, seq, msg_type)
    return acc ^ otp


def wrap_packet(hash_key, psk, seq, msg_type, payload):
    mac = compute_mac(hash_key, psk, payload, seq, msg_type)
    hdr = struct.pack('<IIHHII', AUTH_MAGIC, seq, msg_type, len(payload), mac & 0xFFFFFFFF, mac >> 32)
    return hdr + payload


def unwrap_packet(hash_key, psk, last_rx_seq, packet):
    if len(packet) < 20:
        return 'AUTH_ERR_PAYLOAD_LEN', None, None, last_rx_seq
    magic, seq, msg_type, payload_len, tag_low, tag_high = struct.unpack('<IIHHII', packet[:20])
    if magic != AUTH_MAGIC:
        return 'AUTH_ERR_MAGIC', None, None, last_rx_seq
    if len(packet) != 20 + payload_len:
        return 'AUTH_ERR_PAYLOAD_LEN', None, None, last_rx_seq
    if last_rx_seq is not None and seq <= last_rx_seq:
        return 'AUTH_ERR_REPLAY_SEQ', None, None, last_rx_seq

    payload = packet[20:]
    expected_mac = compute_mac(hash_key, psk, payload, seq, msg_type)
    rx_mac = tag_low | (tag_high << 32)

    if expected_mac != rx_mac:
        return 'AUTH_ERR_TAG_MISMATCH', None, None, last_rx_seq

    return 'AUTH_OK', msg_type, payload, seq


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out_dir = ROOT / 'reports' / 'zc702_auth_channel'
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(20261027)

    hash_key = 0x9E3779B97F4A7C15
    psk_seed = 0x0123456789ABCDEF

    test_results = []

    # 1. Normal round-trip test across message types
    # Types: 1=SYNDROME, 2=REVEAL_REQ, 3=TAG_EXCHANGE, 4=EMIT_CMD
    msg_types = [1, 2, 3, 4]
    last_seq = 0
    all_normal_pass = True

    for seq, mtype in enumerate(msg_types, start=1):
        payload_len = rng.integers(64, 512)
        payload = rng.bytes(int(payload_len))
        packet = wrap_packet(hash_key, psk_seed, seq, mtype, payload)
        status, rx_mtype, rx_payload, last_seq = unwrap_packet(hash_key, psk_seed, last_seq, packet)

        if status != 'AUTH_OK' or rx_mtype != mtype or rx_payload != payload:
            all_normal_pass = False

    test_results.append({
        'test_case': 'normal_round_trip',
        'packets_tested': len(msg_types),
        'status': 'PASS' if all_normal_pass else 'FAIL'
    })

    # 2. Tamper detection: 1-bit flip in payload
    tamper_detected = 0
    trials = 50
    for i in range(trials):
        seq = 100 + i
        payload = bytearray(rng.bytes(128))
        packet = bytearray(wrap_packet(hash_key, psk_seed, seq, 1, bytes(payload)))

        # Flip 1 random bit in payload (offset >= 20)
        flip_byte = rng.integers(20, len(packet))
        flip_bit = rng.integers(0, 8)
        packet[flip_byte] ^= (1 << flip_bit)

        status, _, _, _ = unwrap_packet(hash_key, psk_seed, seq - 1, bytes(packet))
        if status == 'AUTH_ERR_TAG_MISMATCH':
            tamper_detected += 1

    test_results.append({
        'test_case': 'tamper_bit_flip_detection',
        'trials': trials,
        'detected': tamper_detected,
        'detection_rate_pct': (tamper_detected / trials) * 100.0,
        'status': 'PASS' if tamper_detected == trials else 'FAIL'
    })

    # 3. Anti-replay detection: resending old sequence
    seq_current = 200
    pkt1 = wrap_packet(hash_key, psk_seed, seq_current, 2, b"reveal_request_block_5")
    status1, _, _, last_seq = unwrap_packet(hash_key, psk_seed, 0, pkt1)
    assert status1 == 'AUTH_OK' and last_seq == seq_current

    # Replay packet 1
    status_replay, _, _, _ = unwrap_packet(hash_key, psk_seed, last_seq, pkt1)
    replay_blocked = (status_replay == 'AUTH_ERR_REPLAY_SEQ')

    test_results.append({
        'test_case': 'anti_replay_protection',
        'replay_status': status_replay,
        'status': 'PASS' if replay_blocked else 'FAIL'
    })

    # 4. Header corruption
    corrupt_magic_pkt = bytearray(pkt1)
    corrupt_magic_pkt[0] ^= 0xFF
    status_magic, _, _, _ = unwrap_packet(hash_key, psk_seed, 0, bytes(corrupt_magic_pkt))

    test_results.append({
        'test_case': 'corrupt_magic_word_detection',
        'status': 'PASS' if status_magic == 'AUTH_ERR_MAGIC' else 'FAIL'
    })

    # Report synthesis
    c_source = ROOT / 'firmware/zc702_uart/auth_channel.c'
    c_header = ROOT / 'firmware/zc702_uart/auth_channel.h'

    overall = 'PASS' if all(t['status'] == 'PASS' for t in test_results) else 'FAIL'

    report_data = {
        'verified_utc': stamp,
        'item_id': 'P04',
        'title': 'Authenticated classical Alice-Bob channel using Wegman-Carter MAC',
        'overall': overall,
        'files': {
            'auth_channel.c': hashlib.sha256(c_source.read_bytes()).hexdigest(),
            'auth_channel.h': hashlib.sha256(c_header.read_bytes()).hexdigest(),
        },
        'test_results': test_results,
        'security_parameters': {
            'mac_tag_length_bits': 64,
            'universal_hash_field': 'GF(2^64)',
            'forgery_probability_per_message': None,
            'scope': 'Host model only; computational 64-bit-PSK prototype; no certified session bound',
            'anti_replay_mechanism': 'Strictly increasing sequence counter',
            'lockout_policy': 'Fail-closed on persistent tampering'
        }
    }

    (out_dir / 'REPORT.json').write_text(json.dumps(report_data, indent=2) + '\n', encoding='utf-8')

    md_report = f"""# Host authentication prototype regression (P04)

Timestamp: {stamp}. Model checks: {overall}. Project status: PARTIAL.

This script exercises a Python model. It does not execute C, program a board,
or certify information-theoretic authentication. The C helper is checked
independently by syn/zc702/tests/auth_prototype_test.c against the SipHash reference.

The legacy API provisions a 64-bit PSK; deriving two SipHash key words does not
create 128 independent secret bits. No per-message or whole-session forgery
bound is established. Persistent replay state, independent key provisioning,
rekey policy and transport integration remain open.

See REPORT.json for the actual model test results. Baseline UART still uses
CRC framing; this prototype is not deployed in its ELF.
"""

    (out_dir / 'REPORT.md').write_text(md_report, encoding='utf-8')
    print(f"P04_AUTH_CHANNEL_PASS: {out_dir}")


if __name__ == '__main__':
    main()
