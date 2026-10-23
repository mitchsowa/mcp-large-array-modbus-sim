#!/usr/bin/env bash
# Boot the simulator headless and verify key registers over the wire.
# Exit 0 = pass. Used by humans and Claude Code alike after any change.
set -euo pipefail
cd "$(dirname "$0")/.."

# 50502 is the production port. The MCPLA VM NAT-forwards it on this host,
# so the smoke server uses 50512 and the client follows.
PORT=50512
python3 run_sim.py --no-repl --port "$PORT" >/tmp/mcpla-sim-smoke.log 2>&1 &
SIM=$!
trap 'kill $SIM 2>/dev/null || true' EXIT
sleep 4

PORT="$PORT" python3 - <<'PYEOF'
import os, struct, sys
from pymodbus.client import ModbusTcpClient

c = ModbusTcpClient("127.0.0.1", port=int(os.environ["PORT"]), timeout=5)
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
    ("run_enable (hardcoded 0)", i16(10502), 0),
    ("state (idle 6 + mb 16)", i16(10503), 22),
    ("state copy at 10504", i16(10504), 22),
    ("mcpalarm", i16(10505), 0),
    ("unit_count", i16(10506), 50),
    ("num_running_units", i16(10507), 2),
    ("config.lwt", f32(10508), 121.0),
    ("config.setpoint", f32(10510), 120.0),
    ("cut_inout (cut_in)", f32(10520), 119.0),
    ("sensor.1", f32(10522), 111.0),
    ("sensor.14", f32(10548), 124.0),
    ("comp.50", i16(10649), 5000),
    ("run_backup", i16(10650), 0),
    ("mcpwarn", i16(10857), 0),
    ("load_relay_state", i16(10858), 0),
    ("backup_relay_state", i16(10860), 0),
]
fails = 0
for label, got, want in checks:
    ok = abs(got - want) < 0.01
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<26} got {got} want {want}")

# every register in 10501-10860 must answer; a None cache cell used to drop the TCP response
for base in range(10501, 10861, 100):
    count = min(100, 10861 - base)
    blk = c.read_holding_registers(address=base - 1, count=count, slave=1)
    ok = (not blk.isError()) and len(blk.registers) == count
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  block {base}+{count}")

# write path: cut_inout float write must land in config.cut_in/cut_out.
# dev's setValues keeps only the high word (low forced 0); 132.0 encodes as 0x43040000.
raw = struct.unpack(">HH", struct.pack(">f", 132.0))
wr = c.write_registers(address=10519, values=list(raw), slave=1)
assert not wr.isError(), "cut_inout write failed"
import time; time.sleep(2)
rb = f32(10520)
ok = abs(rb - 132.0) < 0.01
fails += not ok
print(f"  {'PASS' if ok else 'FAIL'}  {'cut_inout write round-trip':<26} got {rb} want 132.0")

c.close()
sys.exit(1 if fails else 0)
PYEOF
echo "smoke: ALL PASS"
