#!/usr/bin/env bash
#
# mbtest.sh - read and decode the NWHS Modbus register map (resources/config/01_modbus.json)
#
# Reads all data points from the NWHSModbusServer, labels them per
# 01_modbus.json, decodes 32-bit float register pairs, and writes the
# results to the screen and to a timestamped log file per run.
#
# Usage: mbtest.sh [-H host] [-p port] [-u unit] [-o outdir] [-s] [-z 0|1|auto]
#
#   -H host    server address                (default: 127.0.0.1)
#   -p port    TCP port                      (default: 50502)
#   -u unit    Modbus unit/slave id          (default: 1)
#   -o outdir  directory for log files       (default: .)
#   -s         swap float word order (default is hi-word-first / big endian)
#   -z mode    address offset: 0 = request addr == map addr (zero_mode on)
#              1 = request addr = map addr - 1 (pymodbus default zero_mode off)
#              auto = probe and detect        (default: auto)
#
set -euo pipefail

HOST="127.0.0.1"
PORT="50502"
UNIT="1"
OUTDIR="."
SWAP="0"
ZMODE="auto"

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//' | sed -n '3,17p'; exit 1; }

while getopts "H:p:u:o:sz:h" opt; do
    case "$opt" in
        H) HOST="$OPTARG" ;;
        p) PORT="$OPTARG" ;;
        u) UNIT="$OPTARG" ;;
        o) OUTDIR="$OPTARG" ;;
        s) SWAP="1" ;;
        z) ZMODE="$OPTARG" ;;
        h|*) usage ;;
    esac
done

command -v python3 >/dev/null 2>&1 || { echo "error: python3 not found" >&2; exit 2; }
python3 -c 'import pymodbus' 2>/dev/null || {
    echo "error: pymodbus not installed (pip install pymodbus --break-system-packages)" >&2
    exit 2
}

mkdir -p "$OUTDIR"
OUTFILE="$OUTDIR/mbtest-$(hostname -s)-$(date +%Y%m%d-%H%M%S).log"

ROOT=$(cd "$(dirname "$0")" && pwd)
export MB_HOST="$HOST" MB_PORT="$PORT" MB_UNIT="$UNIT" MB_SWAP="$SWAP" MB_ZMODE="$ZMODE"
export MB_MAP="$ROOT/resources/config/01_modbus.json"

python3 - <<'PYEOF' | tee "$OUTFILE"
import json
import os
import struct
import sys
import time

from pymodbus.client import ModbusTcpClient

HOST  = os.environ["MB_HOST"]
PORT  = int(os.environ["MB_PORT"])
UNIT  = int(os.environ["MB_UNIT"])
SWAP  = os.environ["MB_SWAP"] == "1"
ZMODE = os.environ["MB_ZMODE"]

# ---------------------------------------------------------------- register map
# loaded from resources/config/01_modbus.json so a dev resync updates labels
# kind: int | float (hi word, value spans addr and addr+1) | float_lo
with open(os.environ["MB_MAP"]) as fh:
    params = json.load(fh)["parameters"]

PMAP = {}
for addr in sorted(int(k) for k in params if str(k).isdigit()):
    mapping = params[str(addr)]
    if mapping == "float":
        prev = PMAP.get(addr - 1, ("float", "int"))[0]
        PMAP[addr] = (prev, "float_lo")
    elif isinstance(mapping, dict):
        kind = "float" if mapping.get("type") == "float" else "int"
        PMAP[addr] = (str(mapping.get("key", addr)), kind)
    else:
        PMAP[addr] = (str(mapping), "int")

ADDRS = sorted(PMAP)
LO, HI = ADDRS[0], ADDRS[-1]

# ---------------------------------------------------------------- client setup
def read(client, addr, count):
    """read_holding_registers with kwarg compat across pymodbus 3.x."""
    for kw in ({"device_id": UNIT}, {"slave": UNIT}, {"unit": UNIT}):
        try:
            return client.read_holding_registers(address=addr, count=count, **kw)
        except TypeError:
            continue
    return client.read_holding_registers(addr, count)

client = ModbusTcpClient(HOST, port=PORT, timeout=5)
if not client.connect():
    print(f"FATAL: cannot connect to {HOST}:{PORT}", file=sys.stderr)
    sys.exit(3)

# offset probe: with pymodbus server zero_mode=False (this server's default),
# request address A hits datastore A+1, so we must request map_addr - 1.
if ZMODE == "auto":
    rr = read(client, LO - 1, 1)
    offset = -1 if (rr is not None and not rr.isError()) else 0
    detected = f"auto-detected ({'zero_mode off, requesting addr-1' if offset else 'zero_mode on, direct'})"
else:
    offset = -1 if ZMODE == "1" else 0
    detected = "forced"

# ---------------------------------------------------------------- bulk read
values = {}   # map addr -> int register value or "ERR"
CHUNK = 100   # modbus fc3 max is 125 regs per request

for base in range(LO, HI + 1, CHUNK):
    count = min(CHUNK, HI - base + 1)
    rr = read(client, base + offset, count)
    if rr is not None and not rr.isError():
        for i, v in enumerate(rr.registers):
            values[base + i] = v
    else:
        # block failed -- fall back to per-register reads to isolate
        for a in range(base, base + count):
            r1 = read(client, a + offset, 1)
            if r1 is not None and not r1.isError():
                values[a] = r1.registers[0]
            else:
                values[a] = "ERR"

client.close()

# ---------------------------------------------------------------- decode + print
def to_s16(v):
    return v - 65536 if v >= 32768 else v

def f32(hi, lo):
    if SWAP:
        hi, lo = lo, hi
    return struct.unpack(">f", struct.pack(">HH", hi, lo))[0]

print(f"# mbtest  {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"# target  {HOST}:{PORT}  unit {UNIT}")
print(f"# offset  {offset:+d} ({detected})  float words {'lo-hi (swapped)' if SWAP else 'hi-lo'}")
print(f"# range   {LO}-{HI}  ({len(ADDRS)} registers)")
print()
print(f"{'addr':>6}  {'label':<20} {'value':>14}   raw")
print("-" * 60)

errors = 0
for a in ADDRS:
    label, kind = PMAP[a]
    v = values.get(a, "ERR")
    if v == "ERR":
        errors += 1
        print(f"{a:>6}  {label:<20} {'READ ERROR':>14}")
        continue
    if kind == "float":
        v2 = values.get(a + 1, "ERR")
        if v2 == "ERR":
            errors += 1
            print(f"{a:>6}  {label:<20} {'PAIR ERROR':>14}   0x{v:04X} ----")
        else:
            print(f"{a:>6}  {label:<20} {f32(v, v2):>14.3f}   0x{v:04X} 0x{v2:04X}")
    elif kind == "float_lo":
        continue
    else:
        print(f"{a:>6}  {label:<20} {to_s16(v):>14}   0x{v:04X}")

print("-" * 60)
print(f"# done: {len(ADDRS)} registers, {errors} errors")
sys.exit(0 if errors == 0 else 4)
PYEOF

rc=${PIPESTATUS[0]}
echo
echo "log written to: $OUTFILE"
exit "$rc"
