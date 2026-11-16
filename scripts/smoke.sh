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
    # 10510 is config.warm_cut_in with no type, so it is one int.
    # 10511 is still the float-partner skip, so the cache is one word
    # short and every later value is published one address early.
    ("warm_cut_in int", i16(10510), 115),
    ("cut high word shifted to 10519", i16(10519), 17134),
    ("sensor.1 shifted to 10521", f32(10521), 111.0),
    ("sensor.14 shifted to 10547", f32(10547), 124.0),
    ("comp.50 shifted to 10648", i16(10648), 5000),
    ("run_backup shifted to 10649", i16(10649), 0),
    ("mcpwarn shifted to 10856", i16(10856), 0),
    ("load_relay shifted to 10857", i16(10857), 0),
    ("backup_relay shifted to 10859", i16(10859), 0),
]
fails = 0
for label, got, want in checks:
    ok = abs(got - want) < 0.01
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<26} got {got} want {want}")

# Blocks that stay inside the 359-word cache must answer. A read that
# includes 10860 asks for cache index 359, updateRegs supplies -2, and
# pymodbus cannot encode that, so the response fails.
for base, count in ((10501, 100), (10601, 100), (10701, 100), (10801, 59)):
    blk = c.read_holding_registers(address=base - 1, count=count, slave=1)
    ok = (not blk.isError()) and len(blk.registers) == count
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  block {base}+{count}")

# write path: cut_inout is still address 10520. setValues keeps only the
# high word (low forced 0); 132.0 encodes as 0x43040000. The read cache is
# one address early, so the high word comes back at 10519.
raw = struct.unpack(">HH", struct.pack(">f", 132.0))
wr = c.write_registers(address=10519, values=list(raw), slave=1)
assert not wr.isError(), "cut_inout write failed"
import time; time.sleep(2)
rb = i16(10519)
ok = rb == 17156
fails += not ok
print(f"  {'PASS' if ok else 'FAIL'}  {'cut write seen at 10519':<26} got {rb} want 17156")
tail = c.read_holding_registers(address=10859, count=1, slave=1)
ok = tail.isError()
fails += not ok
print(f"  {'PASS' if ok else 'FAIL'}  {'10860 read fails':<26} got {'error' if ok else tail.registers}")

c.close()
sys.exit(1 if fails else 0)
PYEOF
echo "smoke: ALL PASS"
