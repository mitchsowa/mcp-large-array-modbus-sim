#!/usr/bin/env bash
# Boot the simulator headless and verify key registers over the wire.
# Exit 0 = pass. Used by humans and Claude Code alike after any change.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 run_sim.py --no-repl --fix-10504 >/tmp/mcpla-sim-smoke.log 2>&1 &
SIM=$!
trap 'kill $SIM 2>/dev/null || true' EXIT
sleep 4

python3 - <<'PYEOF'
import struct, sys
from pymodbus.client import ModbusTcpClient

c = ModbusTcpClient("127.0.0.1", port=50502, timeout=5)
assert c.connect(), "cannot connect"

def i16(a):
    r = c.read_holding_registers(address=a - 1, count=1, slave=1)
    assert not r.isError(), f"read {a} failed"
    return r.registers[0]

def f32(a):
    r = c.read_holding_registers(address=a - 1, count=2, slave=1)
    assert not r.isError(), f"read {a} failed"
    return struct.unpack(">f", struct.pack(">HH", *r.registers))[0]

checks = [
    ("on (stop=true default)", i16(10501), 0),
    ("unit_count", i16(10505), 50),
    ("config.lwt", f32(10507), 121.0),
    ("config.setpoint", f32(10509), 120.0),
    ("cut_inout (cut_in)", f32(10519), 119.0),
    ("sensor.1", f32(10521), 111.0),
    ("sensor.14", f32(10547), 124.0),
    ("comp.50", i16(10649), 5000),
]
fails = 0
for label, got, want in checks:
    ok = abs(got - want) < 0.01
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<26} got {got} want {want}")

# write path: cut_inout float write must land in config.cut_in/cut_out
raw = struct.unpack(">HH", struct.pack(">f", 132.0))
wr = c.write_registers(address=10518, values=list(raw), slave=1)
assert not wr.isError(), "cut_inout write failed"
import time; time.sleep(2)
rb = f32(10519)
ok = abs(rb - 132.0) < 0.01
fails += not ok
print(f"  {'PASS' if ok else 'FAIL'}  {'cut_inout write round-trip':<26} got {rb} want 132.0")

c.close()
sys.exit(1 if fails else 0)
PYEOF
echo "smoke: ALL PASS"
