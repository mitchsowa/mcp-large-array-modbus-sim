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
for addr, label in [(10501, "on"), (10502, "run_enable"), (10503, "state"),
                    (10504, "state"), (10505, "mcpalarm"), (10506, "unit_count"),
                    (10507, "num_running_units"), (10650, "run_backup"),
                    (10857, "mcpwarn"), (10858, "load_relay_state")]:
    v = rd(c, addr)
    print(f"  {addr} {label:<20} {v[0] if v else 'READ ERROR'}")
for addr, label in [(10508, "config.lwt"), (10510, "config.setpoint"),
                    (10520, "cut_inout"), (10522, "sensor.1"), (10548, "sensor.14")]:
    v = rd(c, addr, 2)
    print(f"  {addr} {label:<20} {f32(*v) if v else 'READ ERROR'}")
for addr, label in [(10550, "alarm1.1"), (10600, "comp.1"), (10649, "comp.50"),
                    (10657, "alarm2.1"), (10807, "ustatus.1"), (10860, "backup_relay_state")]:
    v = rd(c, addr)
    print(f"  {addr} {label:<20} {v[0] if v else 'READ ERROR'}")
# full span, in chunks: a None cache cell used to drop the TCP response
for base in range(10501, 10861, 100):
    count = min(100, 10861 - base)
    v = rd(c, base, count)
    print(f"  block {base}+{count:<3} {'OK' if v and len(v) == count else 'READ ERROR'}")
if "--write-cut" in sys.argv:
    val = float(sys.argv[sys.argv.index("--write-cut") + 1])
    raw = struct.unpack(">HH", struct.pack(">f", val))
    wr = c.write_registers(address=10520 + OFF, values=list(raw), slave=1)
    print(f"write cut_inout {val} -> {'ERROR' if wr.isError() else 'OK'}")
c.close()
