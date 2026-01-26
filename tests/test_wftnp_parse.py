"""Tests for WFTNP parsing helpers."""

from __future__ import annotations

import struct

from custom_components.wahoo_kickr_core.wftnp import parse_indoor_bike_data


def test_parse_indoor_bike_data_speed_cadence_power() -> None:
    # flags: cadence (bit2) + power (bit6)
    flags = (1 << 2) | (1 << 6)
    speed_raw = 1234  # 12.34 km/h
    cadence_raw = 160  # 80.0 rpm (0.5 rpm units)
    power_raw = 250  # watts

    payload = struct.pack("<H", flags)
    payload += struct.pack("<H", speed_raw)
    payload += struct.pack("<H", cadence_raw)
    payload += struct.pack("<h", power_raw)

    data = parse_indoor_bike_data(payload)

    assert data["speed_kmh"] == 12.34
    assert data["cadence_rpm"] == 80.0
    assert data["power_w"] == 250.0
