import asyncio
import logging
import struct
from types import SimpleNamespace

from s200 import scanner
from s200.mibeacon import SERVICE_UUID, Reading, parse_mac
from tests.test_mibeacon import _encrypt_frame

KEY = bytes(range(16))
MAC = parse_mac("D0:7B:6F:00:00:01")
IDLE = bytes.fromhex("105bcc4d53010000" + "6f7bd0")  # v5, MAC included, no object
DEVICE = SimpleNamespace(address="6EA25FF0-3DD2-44B7-5F88-9A0D7167B173")


class FakeScanner:
    """Stands in for BleakScanner; each instance replays `script` once entered."""

    instances: list["FakeScanner"] = []
    script: list[tuple[float, bytes]] = []

    def __init__(self, detection_callback):
        self.callback = detection_callback
        self.task: asyncio.Task | None = None
        FakeScanner.instances.append(self)

    async def _replay(self):
        for delay, data in FakeScanner.script:
            await asyncio.sleep(delay)
            self.callback(DEVICE, SimpleNamespace(service_data={SERVICE_UUID: data}, rssi=-53))

    async def __aenter__(self):
        self.task = asyncio.create_task(self._replay())
        return self

    async def __aexit__(self, *exc):
        self.task.cancel()


def _run(monkeypatch, script, duration, **kwargs):
    FakeScanner.instances = []
    FakeScanner.script = script
    monkeypatch.setattr(scanner, "BleakScanner", FakeScanner)
    readings: list[Reading] = []

    async def main():
        stop = asyncio.Event()
        asyncio.get_running_loop().call_later(duration, stop.set)
        await scanner.watch(KEY, MAC, readings.append, stop, **kwargs)

    asyncio.run(main())
    return readings


def _weight_frame(kg: float, counter: int = 2) -> bytes:
    obj = b"\x16\x4e\x09" + struct.pack("<BII", 1, round(kg * 100), 1_792_402_176)
    return _encrypt_frame(0x4DCC, counter, obj, MAC, KEY)


def test_watch_delivers_weigh_in(monkeypatch):
    readings = _run(monkeypatch, [(0.01, IDLE), (0.01, _weight_frame(73.4))], 0.1)
    assert readings == [Reading(1, 73.4, 1_792_402_176)]
    assert len(FakeScanner.instances) == 1


def test_watch_restarts_scanner_when_frames_stop(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    # One idle frame then silence: each scanner goes stale and is replaced.
    _run(monkeypatch, [(0.0, IDLE)], 0.35, stale_after=0.08, check_every=0.02)
    assert len(FakeScanner.instances) >= 2
    assert "restarting scanner" in caplog.text


def test_watch_keeps_scanner_while_frames_flow(monkeypatch):
    script = [(0.02, IDLE)] * 15
    _run(monkeypatch, script, 0.25, stale_after=0.1, check_every=0.02)
    assert len(FakeScanner.instances) == 1


def test_watch_warns_when_frame_does_not_decrypt(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    bad = _encrypt_frame(0x4DCC, 3, b"\x16\x4e\x09" + bytes(9), MAC, bytes(16))  # wrong key
    readings = _run(monkeypatch, [(0.01, bad)], 0.05)
    assert readings == []
    assert "could not be decrypted" in caplog.text


def test_watch_ignores_status_object_quietly(monkeypatch, caplog):
    # The S200 sends object 0x6623 about every 50 minutes; it is not a weigh-in.
    caplog.set_level(logging.WARNING)
    status = _encrypt_frame(0x4DCC, 4, bytes.fromhex("23660100"), MAC, KEY)
    readings = _run(monkeypatch, [(0.01, status)], 0.05)
    assert readings == []
    assert caplog.text == ""


def test_watch_logs_scale_waking_once_per_burst(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    script = [(0.01, IDLE)] * 3 + [(0.1, IDLE)]
    _run(monkeypatch, script, 0.2, awake_gap=0.05)
    assert caplog.text.count("scale awake: counter=83") == 2


def test_watch_logs_heartbeat(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    _run(monkeypatch, [(0.01, IDLE)] * 3, 0.15, check_every=0.02, heartbeat_every=0.05)
    assert "heartbeat:" in caplog.text
