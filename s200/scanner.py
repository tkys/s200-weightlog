"""BLE scanning with bleak: hand S200 service data to the decoder."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from s200.mibeacon import SERVICE_UUID, Reading, decode_s200, parse_frame, parse_mac

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
) -> None:
    """Scan forever (or until `stop` is set), calling on_reading per decoded weigh-in."""

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        data = adv.service_data.get(SERVICE_UUID)
        if not data:
            return
        macs = [mac]
        if (addr := _address_mac(device)) is not None:
            macs.append(addr)
        reading = decode_s200(data, bindkey, macs)
        if reading is not None:
            on_reading(reading)

    async with BleakScanner(detection_callback=callback):
        await (stop or asyncio.Event()).wait()


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
