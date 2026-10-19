import struct

import pytest

from s200.mibeacon import (
    Reading,
    decode_s200,
    decode_weight,
    iter_objects,
    parse_frame,
    parse_mac,
)

# Real S200 advertisement from Bluetooth-Devices/xiaomi-ble tests/test_parser.py
S200_ADV = b"HY\x04L\x01\x9a\x80\xa2u\x93\x90\x10\xf0\xab\xc4\xfa\xdc\x06\x00\x00=)\xc0D"
S200_MAC = parse_mac("D0:7B:6F:27:D7:29")
S200_KEY = bytes.fromhex("653b1b10e1cb35e4ac5e60fa45f3bf29")


def test_parse_frame_header():
    frame = parse_frame(S200_ADV)
    assert frame is not None
    assert frame.version == 5
    assert frame.product_id == 0x4C04
    assert frame.encrypted and frame.has_object
    assert frame.mac is None


def test_decode_real_s200_packet():
    reading = decode_s200(S200_ADV, S200_KEY, [S200_MAC])
    assert reading is not None
    assert reading.weight_kg == pytest.approx(62.25)


def test_wrong_bindkey_returns_none():
    assert decode_s200(S200_ADV, bytes(16), [S200_MAC]) is None


def test_wrong_mac_returns_none():
    assert decode_s200(S200_ADV, S200_KEY, [parse_mac("00:11:22:33:44:55")]) is None


def test_tries_mac_candidates_in_order():
    wrong = parse_mac("00:11:22:33:44:55")
    assert decode_s200(S200_ADV, S200_KEY, [wrong, S200_MAC]) is not None


def test_idle_frame_without_object_returns_none():
    # frame control 0x5810: v5, MAC included, no object, not encrypted
    idle = b"\x10\x58\x04\x4c\x07" + S200_MAC[::-1]
    frame = parse_frame(idle)
    assert frame is not None and frame.mac == S200_MAC
    assert decode_s200(idle, S200_KEY, [S200_MAC]) is None


def test_other_product_ignored():
    other = S200_ADV[:2] + b"\x98\x00" + S200_ADV[4:]
    assert decode_s200(other, S200_KEY, [S200_MAC]) is None


def test_truncated_frame_returns_none():
    assert parse_frame(b"HY\x04") is None
    assert decode_s200(S200_ADV[:8], S200_KEY, [S200_MAC]) is None


def test_decode_weight_object():
    value = struct.pack("<BII", 2, 7123, 1_760_000_000)
    assert decode_weight(value) == Reading(profile_id=2, weight_kg=71.23, timestamp=1_760_000_000)
    assert decode_weight(struct.pack("<BII", 1, 0, 1)) is None
    assert decode_weight(b"\x00" * 5) is None


def test_iter_objects_stops_on_corrupt_length():
    payload = b"\x16\x4e\x02\xaa\xbb" + b"\x01\x00\x09\x00"
    assert list(iter_objects(payload)) == [(0x4E16, b"\xaa\xbb")]


def test_parse_mac_rejects_bad_input():
    with pytest.raises(ValueError):
        parse_mac("AA:BB")


def _encrypt_frame(product_id: int, counter: int, payload: bytes, mac: bytes, key: bytes) -> bytes:
    """Build an encrypted v5 frame the way the scale does (inverse of decrypt)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESCCM

    head = b"\x48\x59" + product_id.to_bytes(2, "little") + bytes([counter])
    ext_counter = b"\x00\x00\x00"
    nonce = mac[::-1] + head[2:5] + ext_counter
    sealed = AESCCM(key, tag_length=4).encrypt(nonce, payload, b"\x11")
    return head + sealed[:-4] + ext_counter + sealed[-4:]


def test_ms114_product_0x4dcc_decodes():
    key = bytes(range(16))
    mac = parse_mac("D0:7B:6F:00:00:01")
    obj = b"\x16\x4e\x09" + struct.pack("<BII", 1, 7440, 1_792_402_176)
    adv = _encrypt_frame(0x4DCC, 2, obj, mac, key)
    assert decode_s200(adv, key, [mac]) == Reading(1, 74.4, 1_792_402_176)
