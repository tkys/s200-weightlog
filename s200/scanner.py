"""BLE scanning with bleak: hand S200 service data to the decoder."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from s200.mibeacon import (
    S200_PRODUCT_IDS,
    SERVICE_UUID,
    Reading,
    decode_s200,
    parse_frame,
    parse_mac,
)

log = logging.getLogger(__name__)


def _address_mac(device: BLEDevice) -> bytes | None:
    # Linux/Windows report the real MAC; macOS reports a CoreBluetooth UUID.
    try:
        return parse_mac(device.address)
    except ValueError:
        return None


# No service_uuids filter: on macOS it only matches the advertised UUID list,
# and the S200 carries 0xFE95 as service data only.


async def watch(
    bindkey: bytes,
    mac: bytes,
    on_reading: Callable[[Reading], None],
    stop: asyncio.Event | None = None,
    *,
    stale_after: float = 600,
    check_every: float = 30,
    heartbeat_every: float = 3600,
) -> None:
    """Scan forever (or until `stop` is set), calling on_reading per decoded weigh-in.

    CoreBluetooth scans can go quiet after running for hours. The S200 keeps
    sending idle frames, so if nothing from it arrives for `stale_after`
    seconds the scanner is torn down and started again.
    """
    stop = stop or asyncio.Event()
    loop = asyncio.get_running_loop()
    last_seen = loop.time()
    frames = 0

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        nonlocal last_seen, frames
        data = adv.service_data.get(SERVICE_UUID)
        if not data:
            return
        frame = parse_frame(data)
        if frame is None or frame.product_id not in S200_PRODUCT_IDS:
            return
        last_seen = loop.time()
        frames += 1
        macs = [mac]
        if (addr := _address_mac(device)) is not None:
            macs.append(addr)
        reading = decode_s200(data, bindkey, macs)
        if reading is not None:
            on_reading(reading)
        elif frame.has_object and frame.encrypted:
            log.warning("S200 object frame could not be decoded: %s", data.hex())

    next_heartbeat = loop.time() + heartbeat_every
    while not stop.is_set():
        last_seen = loop.time()
        async with BleakScanner(detection_callback=callback):
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=check_every)
                except TimeoutError:
                    pass
                now = loop.time()
                if now >= next_heartbeat:
                    log.info("heartbeat: %d S200 frames in the last hour", frames)
                    frames = 0
                    next_heartbeat = now + heartbeat_every
                if now - last_seen > stale_after:
                    log.warning("no S200 frames for %.0f s, restarting scanner", now - last_seen)
                    break


async def dump(seconds: float) -> None:
    """Print every MiBeacon advertisement seen, for setup and debugging."""

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        data = adv.service_data.get(SERVICE_UUID)
        if not data:
            return
        frame = parse_frame(data)
        info = "unparsed"
        if frame is not None:
            info = (
                f"product=0x{frame.product_id:04x} v{frame.version} cnt={frame.counter}"
                f" enc={frame.encrypted} obj={frame.has_object}"
            )
            if frame.mac:
                info += f" mac={frame.mac.hex(':').upper()}"
        print(f"{device.address}  rssi={adv.rssi}  {info}  {data.hex()}", flush=True)

    async with BleakScanner(detection_callback=callback):
        await asyncio.sleep(seconds)
