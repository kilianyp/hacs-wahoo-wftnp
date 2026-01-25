"""Wahoo Fitness TNP (WFTNP) client helpers."""

from __future__ import annotations

import asyncio
import socket
import struct
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional, Tuple

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf


# ---------------------------
# BLE UUID helpers (expand 16-bit UUIDs to 128-bit base)
# ---------------------------

def ble16_to_uuid(u16: int) -> uuid.UUID:
    return uuid.UUID(f"0000{u16:04x}-0000-1000-8000-00805f9b34fb")


FTMS_SERVICE_UUID = ble16_to_uuid(0x1826)

# FTMS characteristics
FTMS_CONTROL_POINT_UUID = ble16_to_uuid(0x2AD9)  # Fitness Machine Control Point
FTMS_STATUS_UUID = ble16_to_uuid(0x2ADA)         # Fitness Machine Status (optional)
INDOOR_BIKE_DATA_UUID = ble16_to_uuid(0x2AD2)    # Indoor Bike Data (optional)


# ---------------------------
# WFTNP framing
# Header: Version, MsgType, Seq, RespCode, DataLen(u16 BE)
# MsgType:
#   1 discover services
#   2 discover characteristics
#   3 read characteristic
#   4 write characteristic
#   5 enable notifications
#   6 notification (unsolicited)
# ---------------------------

WFTNP_VERSION = 1
_HDR_STRUCT = struct.Struct("!BBBBH")  # network byte order for DataLen (uint16)


class WFTNPError(RuntimeError):
    """Generic WFTNP error."""


class FTMSControlPointError(RuntimeError):
    """FTMS control point error."""


@dataclass(frozen=True)
class DiscoveredDevice:
    name: str
    host: str
    address: str
    port: int
    properties: Dict[str, str]


class _WahooTNPListener(ServiceListener):
    def __init__(self) -> None:
        self._found: asyncio.Queue[DiscoveredDevice] = asyncio.Queue()

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if not info:
            return

        props: Dict[str, str] = {}
        for k, v in (info.properties or {}).items():
            try:
                ks = k.decode("utf-8", "ignore")
            except Exception:
                continue
            try:
                vs = v.decode("utf-8", "ignore")
            except Exception:
                vs = repr(v)
            props[ks] = vs

        addr = ""
        if info.addresses:
            addr = socket.inet_ntoa(info.addresses[0])

        dev = DiscoveredDevice(
            name=name,
            host=(info.server or "").rstrip("."),
            address=addr,
            port=info.port,
            properties=props,
        )
        try:
            self._found.put_nowait(dev)
        except asyncio.QueueFull:
            pass

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self.add_service(zc, type_, name)


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _ftms_result_to_str(code: int) -> str:
    # Common FTMS Control Point result codes (0x80 responses)
    return {
        0x01: "SUCCESS",
        0x02: "OP_CODE_NOT_SUPPORTED",
        0x03: "INVALID_PARAMETER",
        0x04: "OPERATION_FAILED",
        0x05: "CONTROL_NOT_PERMITTED",
    }.get(code, f"UNKNOWN_RESULT_{code:#04x}")


class WFTNPClient:
    """
    Wi-Fi client for Wahoo/compatible WFTNP (DIRCON / wahoo-fitness-tnp).
    WFTNP is effectively BLE GATT tunneled over TCP.
    """

    def __init__(self) -> None:
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._seq: int = 0
        self._pending: Dict[Tuple[int, int], asyncio.Future[Tuple[int, bytes]]] = {}

        self._rx_task: Optional[asyncio.Task[None]] = None
        self._notify_cb: Optional[Callable[[uuid.UUID, bytes], Awaitable[None] | None]] = None

        # caches
        self.ftms_control_point_uuid: Optional[uuid.UUID] = None

        # incoming control point responses
        self._cp_queue: asyncio.Queue[bytes] = asyncio.Queue()

    # --------- discovery ----------

    @staticmethod
    async def discover(timeout: float = 3.0) -> Dict[str, DiscoveredDevice]:
        zc = Zeroconf()
        listener = _WahooTNPListener()
        stype = "_wahoo-fitness-tnp._tcp.local."
        ServiceBrowser(zc, stype, listener)

        found: Dict[str, DiscoveredDevice] = {}

        async def drain() -> None:
            while True:
                dev = await listener._found.get()
                found[dev.name] = dev

        drain_task = asyncio.create_task(drain())
        try:
            await asyncio.sleep(timeout)
        finally:
            drain_task.cancel()
            try:
                await drain_task
            except asyncio.CancelledError:
                pass
            zc.close()

        return found

    # --------- connection / IO ----------

    async def connect(self, host: str, port: int) -> None:
        self._reader, self._writer = await asyncio.open_connection(host, port)

        # reduce latency (best-effort)
        sock = self._writer.get_extra_info("socket")
        if sock is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass

        self._rx_task = asyncio.create_task(self._rx_loop())

    async def close(self) -> None:
        if self._rx_task:
            self._rx_task.cancel()
            try:
                await self._rx_task
            except asyncio.CancelledError:
                pass
            self._rx_task = None

        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

        self._reader = None
        self._writer = None

    def set_notification_callback(
        self, cb: Optional[Callable[[uuid.UUID, bytes], Awaitable[None] | None]]
    ) -> None:
        self._notify_cb = cb

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    async def _rx_loop(self) -> None:
        assert self._reader is not None

        while True:
            hdr = await self._reader.readexactly(_HDR_STRUCT.size)
            ver, mtype, seq, resp, dlen = _HDR_STRUCT.unpack(hdr)
            data = await self._reader.readexactly(dlen) if dlen else b""

            if ver != WFTNP_VERSION:
                raise WFTNPError(f"Unsupported WFTNP version {ver}")

            if mtype == 6:
                # notification: 16-byte char UUID + value
                if len(data) >= 16:
                    char_uuid = uuid.UUID(bytes=data[:16])
                    value = data[16:]

                    if self.ftms_control_point_uuid and char_uuid == self.ftms_control_point_uuid:
                        # FTMS CP responses arrive here
                        self._cp_queue.put_nowait(value)

                    if self._notify_cb:
                        out = self._notify_cb(char_uuid, value)
                        if asyncio.iscoroutine(out):
                            asyncio.create_task(out)
                continue

            fut = self._pending.pop((mtype, seq), None)
            if fut and not fut.done():
                fut.set_result((resp, data))

    async def _request(self, mtype: int, payload: bytes) -> Tuple[int, bytes]:
        assert self._writer is not None

        seq = self._next_seq()
        hdr = _HDR_STRUCT.pack(WFTNP_VERSION, mtype, seq, 0, len(payload))
        fut: asyncio.Future[Tuple[int, bytes]] = asyncio.get_running_loop().create_future()
        self._pending[(mtype, seq)] = fut

        self._writer.write(hdr + payload)
        await self._writer.drain()

        resp_code, data = await fut
        if resp_code != 0:
            raise WFTNPError(f"WFTNP request failed: type={mtype} resp_code={resp_code}")
        return resp_code, data

    # --------- WFTNP operations ----------

    async def discover_services(self) -> list[uuid.UUID]:
        _, data = await self._request(1, b"")
        if len(data) % 16 != 0:
            raise WFTNPError(f"Malformed Discover Services response len={len(data)}")
        return [uuid.UUID(bytes=data[i:i + 16]) for i in range(0, len(data), 16)]

    async def discover_characteristics(self, service_uuid: uuid.UUID) -> Dict[uuid.UUID, int]:
        _, data = await self._request(2, service_uuid.bytes)
        if len(data) < 16:
            raise WFTNPError("Malformed Discover Characteristics response")

        svc = uuid.UUID(bytes=data[:16])
        if svc != service_uuid:
            raise WFTNPError(f"Discover Characteristics mismatch svc={svc} expected={service_uuid}")

        recs = data[16:]
        if len(recs) % 17 != 0:
            raise WFTNPError(f"Malformed characteristic records len={len(recs)}")

        out: Dict[uuid.UUID, int] = {}
        for i in range(0, len(recs), 17):
            cu = uuid.UUID(bytes=recs[i:i + 16])
            props = recs[i + 16]
            out[cu] = props  # READ=0x01 WRITE=0x02 NOTIFY=0x04 (as commonly used in WFTNP)
        return out

    async def read_characteristic(self, char_uuid: uuid.UUID) -> bytes:
        _, data = await self._request(3, char_uuid.bytes)
        if len(data) < 16:
            raise WFTNPError("Malformed Read Characteristic response")
        cu = uuid.UUID(bytes=data[:16])
        if cu != char_uuid:
            raise WFTNPError("Read Characteristic UUID mismatch")
        return data[16:]

    async def write_characteristic(self, char_uuid: uuid.UUID, value: bytes) -> None:
        await self._request(4, char_uuid.bytes + value)

    async def enable_notifications(self, char_uuid: uuid.UUID, enable: bool = True) -> None:
        await self._request(5, char_uuid.bytes + (b"\x01" if enable else b"\x00"))

    # --------- FTMS convenience ----------

    async def ftms_init(
        self,
        *,
        subscribe_indoor_bike_data: bool = True,
        subscribe_status: bool = False,
    ) -> None:
        services = await self.discover_services()
        if FTMS_SERVICE_UUID not in services:
            raise WFTNPError(f"FTMS service {FTMS_SERVICE_UUID} not found")

        chars = await self.discover_characteristics(FTMS_SERVICE_UUID)

        if FTMS_CONTROL_POINT_UUID not in chars:
            raise WFTNPError("FTMS control point characteristic (0x2AD9) not found")
        self.ftms_control_point_uuid = FTMS_CONTROL_POINT_UUID
        await self.enable_notifications(self.ftms_control_point_uuid, True)

        if subscribe_indoor_bike_data and INDOOR_BIKE_DATA_UUID in chars:
            await self.enable_notifications(INDOOR_BIKE_DATA_UUID, True)

        if subscribe_status and FTMS_STATUS_UUID in chars:
            await self.enable_notifications(FTMS_STATUS_UUID, True)

    async def _await_cp_result(self, expected_req_opcode: int, timeout: float = 2.0) -> None:
        """
        Wait for FTMS Control Point response:
          0x80, <req_opcode>, <result_code>
        Raise on anything except SUCCESS (0x01).
        """
        while True:
            pkt = await asyncio.wait_for(self._cp_queue.get(), timeout=timeout)
            if len(pkt) >= 3 and pkt[0] == 0x80 and pkt[1] == expected_req_opcode:
                result = pkt[2]
                if result != 0x01:
                    raise FTMSControlPointError(
                        f"FTMS opcode {expected_req_opcode:#04x} failed: {_ftms_result_to_str(result)}"
                    )
                return

    async def zwift_like_handshake(self) -> None:
        # Common “become controller” sequence
        await self.request_control()
        await self.reset()
        await self.request_control()
        await self.start_training()

    # --- FTMS opcodes ---

    async def request_control(self) -> None:
        assert self.ftms_control_point_uuid is not None
        await self.write_characteristic(self.ftms_control_point_uuid, b"\x00")
        await self._await_cp_result(0x00)

    async def reset(self) -> None:
        assert self.ftms_control_point_uuid is not None
        await self.write_characteristic(self.ftms_control_point_uuid, b"\x01")
        await self._await_cp_result(0x01)

    async def start_training(self) -> None:
        assert self.ftms_control_point_uuid is not None
        await self.write_characteristic(self.ftms_control_point_uuid, b"\x07")
        await self._await_cp_result(0x07)

    async def stop_training(self) -> None:
        """
        Not all devices support this opcode; if unsupported you'll get OP_CODE_NOT_SUPPORTED.
        """
        assert self.ftms_control_point_uuid is not None
        await self.write_characteristic(self.ftms_control_point_uuid, b"\x08")
        await self._await_cp_result(0x08)

    # --- high-level helpers ---

    async def set_erg_watts(self, watts: int, *, min_watts: int = 0, max_watts: int = 600) -> None:
        """
        Set Target Power (ERG).
        Payload: 0x05 + uint16 LE watts.
        """
        watts_i = int(clamp(float(watts), float(min_watts), float(max_watts)))
        assert self.ftms_control_point_uuid is not None
        payload = b"\x05" + struct.pack("<H", watts_i)
        await self.write_characteristic(self.ftms_control_point_uuid, payload)
        await self._await_cp_result(0x05)

    async def set_grade(
        self,
        grade_percent: float,
        *,
        wind_mps: float = 0.0,
        crr: float = 0.0040,
        cw: float = 0.510,
        min_grade: float = -10.0,
        max_grade: float = 15.0,
    ) -> None:
        """
        Set Indoor Bike Simulation Parameters (SIM).
        Payload: 0x11 + wind(int16) + grade(int16) + crr(uint8) + cw(uint8)

        Common scalings:
          wind_speed_raw = wind_mps * 1000   (0.001 m/s)
          grade_raw      = grade_percent * 100 (0.01 %)
          crr_raw        = crr * 10000       (0.0001)
          cw_raw         = cw * 100          (0.01 kg/m)

        Note: crr/cw are 1-byte fields, so we clamp into 0..255.
        """
        g = clamp(float(grade_percent), min_grade, max_grade)
        w = clamp(float(wind_mps), -50.0, 50.0)  # sanity clamp
        crr_f = clamp(float(crr), 0.0, 0.0255)   # 0..255/10000
        cw_f = clamp(float(cw), 0.0, 2.55)       # 0..255/100

        wind_raw = int(round(w * 1000.0))
        grade_raw = int(round(g * 100.0))
        crr_raw = int(round(crr_f * 10000.0))
        cw_raw = int(round(cw_f * 100.0))

        # clamp to int16 / uint8 ranges
        wind_raw = int(clamp(wind_raw, -32768, 32767))
        grade_raw = int(clamp(grade_raw, -32768, 32767))
        crr_raw = int(clamp(crr_raw, 0, 255))
        cw_raw = int(clamp(cw_raw, 0, 255))

        assert self.ftms_control_point_uuid is not None
        payload = b"\x11" + struct.pack("<hhBB", wind_raw, grade_raw, crr_raw, cw_raw)
        await self.write_characteristic(self.ftms_control_point_uuid, payload)
        await self._await_cp_result(0x11)


# ---------------------------
# Optional: Indoor Bike Data parsing (very basic)
# ---------------------------

def parse_indoor_bike_data(value: bytes) -> Dict[str, float]:
    """
    FTMS Indoor Bike Data (0x2AD2) starts with flags (uint16 LE),
    followed by fields conditionally present.

    We'll parse a few common ones (speed, cadence, power) when present.
    This is a "best effort" decoder—devices vary in what they include.
    """
    if len(value) < 2:
        return {}

    flags = struct.unpack_from("<H", value, 0)[0]
    i = 2
    out: Dict[str, float] = {}

    def need(n: int) -> bool:
        return i + n <= len(value)

    # instantaneous speed (uint16, 0.01 km/h) - often present even if flags vary
    if need(2):
        inst_speed = struct.unpack_from("<H", value, i)[0]
        out["speed_kmh"] = inst_speed / 100.0
        i += 2

    # average speed
    if (flags & (1 << 1)) and need(2):
        avg_speed = struct.unpack_from("<H", value, i)[0]
        out["avg_speed_kmh"] = avg_speed / 100.0
        i += 2

    # instantaneous cadence (uint16, 0.5 rpm)
    if (flags & (1 << 2)) and need(2):
        cad = struct.unpack_from("<H", value, i)[0]
        out["cadence_rpm"] = cad / 2.0
        i += 2

    # average cadence
    if (flags & (1 << 3)) and need(2):
        cad = struct.unpack_from("<H", value, i)[0]
        out["avg_cadence_rpm"] = cad / 2.0
        i += 2

    # total distance (uint24, meters) sometimes
    if (flags & (1 << 4)) and need(3):
        dist = value[i] | (value[i + 1] << 8) | (value[i + 2] << 16)
        out["distance_m"] = float(dist)
        i += 3

    # resistance level (int16)
    if (flags & (1 << 5)) and need(2):
        lvl = struct.unpack_from("<h", value, i)[0]
        out["resistance_level"] = float(lvl)
        i += 2

    # instantaneous power (int16, watts)
    if (flags & (1 << 6)) and need(2):
        p = struct.unpack_from("<h", value, i)[0]
        out["power_w"] = float(p)
        i += 2

    return out
