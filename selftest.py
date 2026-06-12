#!/usr/bin/env python3
"""HARNESS FILE -- poll the simulator like a BMS gateway would.
Usage: ./selftest.py [host] [--write-cut 132.0]"""
import struct
import sys

from pymodbus.client import ModbusTcpClient

HOST = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "127.0.0.1"
OFF = -1  # zero_mode=False: request addr = map addr - 1


def f32(hi, lo):
    return struct.unpack(">f", struct.pack(">HH", hi, lo))[0]


def rd(c, addr, count=1):
    rr = c.read_holding_registers(address=addr + OFF, count=count, slave=1)
    return None if rr.isError() else rr.registers


c = ModbusTcpClient(HOST, port=50502, timeout=5)
assert c.connect(), f"cannot connect {HOST}:50502"
print(f"target {HOST}:50502 (request offset {OFF})")
for addr, label in [(10501, "on"), (10502, "state"), (10505, "unit_count"),
                    (10506, "num_running_units")]:
    v = rd(c, addr)
    print(f"  {addr} {label:<18} {v[0] if v else 'READ ERROR'}")
for addr, label in [(10507, "config.lwt"), (10509, "config.setpoint"),
                    (10519, "cut_inout"), (10521, "sensor.1"), (10547, "sensor.14")]:
    v = rd(c, addr, 2)
    print(f"  {addr} {label:<18} {f32(*v) if v else 'READ ERROR'}")
for addr, label in [(10549, "alarm.1"), (10600, "comp.1"), (10649, "comp.50")]:
    v = rd(c, addr)
    print(f"  {addr} {label:<18} {v[0] if v else 'READ ERROR'}")
print("probing reg 10504 (alarm.value.value, known-bad in production):")
v = rd(c, 10504)
print(f"  10504 single read     -> {v[0] if v else 'READ ERROR (faithful replication)'}")
if "--write-cut" in sys.argv:
    val = float(sys.argv[sys.argv.index("--write-cut") + 1])
    raw = struct.unpack(">HH", struct.pack(">f", val))
    wr = c.write_registers(address=10519 + OFF, values=list(raw), slave=1)
    print(f"write cut_inout {val} -> {'ERROR' if wr.isError() else 'OK'}")
c.close()
