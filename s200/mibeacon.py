"""Xiaomi MiBeacon v4/v5 decoder for the Xiaomi Smart Scale S200 (MJTZC02YM).

Frame layout and crypto follow Bluetooth-Devices/xiaomi-ble (parser.py).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

SERVICE_UUID = "0000fe95-0000-1000-8000-00805f9b34fb"
# 0x4DCC: xiaomi.scales.ms114, confirmed on a real scale 2026-10-19
S200_PRODUCT_IDS = frozenset({0x4C04, 0x4DCB, 0x4DCC, 0x45C9})
OBJ_WEIGHT = 0x4E16


@dataclass(frozen=True)
class Frame:
    version: int
    product_id: int
    counter: int
    encrypted: bool
    has_object: bool
    mac: bytes | None  # big-endian MAC carried in the frame, if any
    payload_start: int


@dataclass(frozen=True)
class Reading:
    profile_id: int
    weight_kg: float
    timestamp: int  # unix seconds, from the scale's clock


def parse_mac(mac: str) -> bytes:
    raw = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    if len(raw) != 6:
        raise ValueError(f"invalid MAC address: {mac!r}")
    return raw


def parse_frame(data: bytes) -> Frame | None:
    """Parse the MiBeacon header. Returns None for frames we cannot handle."""
    if len(data) < 5:
        return None
    frctrl = int.from_bytes(data[0:2], "little")
    version = frctrl >> 12
    if (frctrl >> 7) & 1 or version < 4:  # mesh, or pre-v4 (legacy crypto)
        return None

    i = 5
    mac = None
    if (frctrl >> 4) & 1:
        if len(data) < i + 6:
            return None
        mac = data[i : i + 6][::-1]
        i += 6
    if (frctrl >> 5) & 1:
        if len(data) < i + 1:
            return None
        capability = data[i]
        i += 1
        if capability & 0x20:
            i += 1
    if len(data) < i:
        return None

    return Frame(
        version=version,
        product_id=int.from_bytes(data[2:4], "little"),
        counter=data[4],
        encrypted=bool((frctrl >> 3) & 1),
        has_object=bool((frctrl >> 6) & 1),
        mac=mac,
        payload_start=i,
    )


def decrypt(data: bytes, frame: Frame, mac: bytes, bindkey: bytes) -> bytes | None:
    """AES-128-CCM decrypt the object payload. None if the tag does not verify."""
    if len(data) < frame.payload_start + 7:
        return None
    nonce = mac[::-1] + data[2:5] + data[-7:-4]
    ciphertext = data[frame.payload_start : -7] + data[-4:]
    try:
        return AESCCM(bindkey, tag_length=4).decrypt(nonce, ciphertext, b"\x11")
    except InvalidTag:
        return None


def iter_objects(payload: bytes):
    """Yield (type, value) pairs from a decrypted TLV payload."""
    pos = 0
    while len(payload) >= pos + 3:
        obj_type = int.from_bytes(payload[pos : pos + 2], "little")
        length = payload[pos + 2]
        end = pos + 3 + length
        if end > len(payload):
            return
        yield obj_type, payload[pos + 3 : end]
        pos = end


def decode_weight(value: bytes) -> Reading | None:
    if len(value) != 9:
        return None
    profile_id, raw, timestamp = struct.unpack("<BII", value)
    if raw == 0:  # stepped off / no measurement
        return None
    return Reading(profile_id=profile_id, weight_kg=raw / 100.0, timestamp=timestamp)


def decrypt_objects(
    data: bytes, bindkey: bytes, macs: list[bytes] | tuple[bytes, ...] = ()
) -> list[tuple[int, bytes]] | None:
    """Decrypt an S200 object frame into its (type, value) objects.

    Returns None when the frame is not an encrypted S200 object frame or no
    candidate MAC decrypts it. `macs` are candidate scale MACs for the nonce
    (macOS hides the real address, so the configured MAC is required unless
    the frame carries one).
    """
    frame = parse_frame(data)
    if frame is None or frame.product_id not in S200_PRODUCT_IDS:
        return None
    if not frame.has_object or not frame.encrypted:
        return None

    candidates = ([frame.mac] if frame.mac else []) + [m for m in macs if m != frame.mac]
    for mac in candidates:
        payload = decrypt(data, frame, mac, bindkey)
        if payload is not None:
            return list(iter_objects(payload))
    return None


def decode_s200(
    data: bytes, bindkey: bytes, macs: list[bytes] | tuple[bytes, ...] = ()
) -> Reading | None:
    """Decode an S200 service-data payload into a Reading (None if it holds no weight)."""
    for obj_type, value in decrypt_objects(data, bindkey, macs) or ():
        if obj_type == OBJ_WEIGHT:
            return decode_weight(value)
    return None
