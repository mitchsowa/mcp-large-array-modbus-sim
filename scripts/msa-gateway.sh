#!/usr/bin/env bash
# HARNESS FILE -- build a FieldServer / MSA gateway CSV from 03_modbus.json.
#
# In that file the object name identifies the row. A numeric object name is
# the Modbus register; a named object stores the register in addr.
# The "key" property is the Python variable (on, config.lwt, state_ub).
# The "type" property is the Modbus register data type: float -> Join_Float
# (high word first), int -> Scale. struct is not the wire type.
# A key of "float" is the low word of the previous float, not its own point.
#
# Usage:
#   ./scripts/msa-gateway.sh [out.csv]
# Default output is prof7tb.csv in the repo root.
# Does not modify any production file.
set -euo pipefail
cd "$(dirname "$0")/.."
out="${1:-prof7tb.csv}"
exec python3 - "$out" <<'PY'
import json
import os
import re
import sys
from collections import Counter

BASE = 10501
END = 10860
BLOCK = 90
ARRAY_LEN = 400
# sprtp 1.8.5 data_map. A changed map must fail here instead of silently
# emitting a different profile.
EXPECT_POINTS = 342
EXPECT_JOIN = 17
EXPECT_SCALE = 325

out = sys.argv[1]
src = "resources/config/03_modbus.json"


def die(msg):
    print(f"msa-gateway: {msg}", file=sys.stderr)
    sys.exit(1)


with open(src, encoding="utf-8") as fh:
    doc = json.load(fh)
data_map = doc.get("data_map")
if not isinstance(data_map, dict) or not data_map:
    die(f"{src} has no data_map object")

rows = []
for obj_name, entry in data_map.items():
    if not isinstance(entry, dict):
        die(f"{obj_name}: entry is not an object")
    key = entry.get("key")
    if not isinstance(key, str) or not key:
        die(f"{obj_name}: key must be the Python variable")
    typ = entry.get("type", "int")
    if typ not in ("int", "float"):
        die(f"{obj_name}: type {typ!r} is not a Modbus int or float")
    addr = entry.get("addr")
    if isinstance(addr, bool) or not isinstance(addr, int):
        die(f"{obj_name}: addr must be an integer")
    if str(obj_name).isdigit():
        reg = int(obj_name)
        if addr != reg - BASE:
            die(f"{obj_name}: addr {addr} is not {reg - BASE} (register - {BASE})")
    else:
        reg = addr
        if reg < BASE:
            die(f"{obj_name}: addr {addr} is not a register")
    writable = entry.get("w", False)
    if not isinstance(writable, bool):
        die(f"{obj_name}: w must be true or false")
    rows.append(
        {"obj": str(obj_name), "reg": reg, "key": key, "type": typ, "w": writable}
    )

rows.sort(key=lambda row: row["reg"])
regs = [row["reg"] for row in rows]
if len(regs) != len(set(regs)):
    die("duplicate register")
if regs != list(range(BASE, END + 1)):
    die(
        f"registers must be {BASE}-{END} with no gaps, "
        f"got {regs[0]}-{regs[-1]} ({len(regs)} rows)"
    )

points = []
for i, row in enumerate(rows):
    if row["key"] == "float":
        prev = rows[i - 1] if i else None
        if prev is None or prev["type"] != "float" or prev["reg"] != row["reg"] - 1:
            print(
                f"msa-gateway: skip {row['reg']} key float; "
                "previous register is not type float",
                file=sys.stderr,
            )
        continue
    if row["type"] == "float":
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if (
            nxt is None
            or nxt["key"] != "float"
            or nxt["reg"] != row["reg"] + 1
        ):
            die(
                f"{row['reg']} type float ({row['key']}) "
                "is not followed by a key float low word"
            )
    points.append(row)

raw_names = []
for point in points:
    name = point["key"].replace(".", "_")
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
        die(f"{point['reg']}: variable {point['key']!r} is not a legal descriptor name")
    raw_names.append(name)
counts = Counter(raw_names)
names = []
for point, name in zip(points, raw_names):
    if counts[name] > 1:
        name = f"{name}_{point['reg']}"
    names.append(name)
    point["name"] = name
if len(names) != len(set(names)):
    die("descriptor names are not unique after the register suffix")
if any("." in name for name in names):
    die("descriptor name contains '.'")

av_id = 0
ai_id = 1
for point in points:
    if point["w"]:
        point["bac"] = "AV"
        point["oid"] = av_id
        av_id += 1
    else:
        point["bac"] = "AI"
        point["oid"] = ai_id
        ai_id += 1

span = END - BASE + 1
if span % BLOCK != 0:
    die(f"span {span} is not a multiple of {BLOCK}")
nblocks = span // BLOCK
if nblocks > 100:
    die("poll count is unreasonable")

polls = []
for block in range(nblocks):
    polls.append(
        {
            "name": f"CMD_Dev_{block:02d}_$node_id",
            "arr": f"DA_U16_{block:02d}_$node_id",
            "off": block * BLOCK,
            "addr": BASE + block * BLOCK,
            "length": BLOCK,
        }
    )

covered = []
for poll in polls:
    covered.extend(range(poll["addr"], poll["addr"] + poll["length"]))
if covered != list(range(BASE, END + 1)):
    die(f"polls do not cover {BASE}-{END} once")

moves = []
for index, point in enumerate(points):
    src_off = point["reg"] - BASE
    words = 2 if point["type"] == "float" else 1
    block = src_off // BLOCK
    if block >= nblocks:
        die(f"{point['reg']} is outside the polls")
    poll = polls[block]
    if poll["off"] > src_off or src_off + words > poll["off"] + poll["length"]:
        die(f"{point['reg']} {point['type']} crosses poll {poll['addr']}")
    dst_block = index // BLOCK
    if dst_block >= nblocks:
        die(f"point {index} needs another DA_Flt array")
    if src_off >= ARRAY_LEN or index >= ARRAY_LEN:
        die(f"offset {src_off}/{index} does not fit array length {ARRAY_LEN}")
    function = "Join_Float" if point["type"] == "float" else "Scale"
    point["index"] = index
    moves.append(
        {
            "src_arr": poll["arr"],
            "src_off": src_off,
            "dst_arr": f"DA_Flt_{dst_block:02d}_$node_id",
            "dst_off": index,
            "function": function,
            "name": point["name"],
        }
    )

n_join = sum(1 for move in moves if move["function"] == "Join_Float")
n_scale = sum(1 for move in moves if move["function"] == "Scale")
if (len(points), n_join, n_scale) != (EXPECT_POINTS, EXPECT_JOIN, EXPECT_SCALE):
    die(
        f"expected {EXPECT_POINTS} points, {EXPECT_JOIN} Join_Float, "
        f"{EXPECT_SCALE} Scale; got {len(points)}, {n_join}, {n_scale}"
    )
if any(move["function"] == "Join_Float_Swapped" for move in moves):
    die("Join_Float_Swapped is the low-word-first packing")

seen_oid = {"AV": set(), "AI": set()}
for point in points:
    if point["oid"] in seen_oid[point["bac"]]:
        die(f"duplicate {point['bac']} object id {point['oid']}")
    seen_oid[point["bac"]].add(point["oid"])


def banner(title):
    bar = "//" + ("=" * 80) + ",,,,,,,,"
    return [
        bar,
        "//,,,,,,,,",
        f"//    {title},,,,,,,,",
        "//,,,,,,,,",
        bar,
    ]


lines = []
lines += banner("prof7tb.csv")
lines += [
    "//,,,,,,,,",
    "//    Generated by scripts/msa-gateway.sh from resources/config/03_modbus.json. Regenerate; do not hand-edit.,,,,,,,,",
    "//    key is the Python variable. type is the Modbus data type: float is Join_Float and int is Scale.,,,,,,,,",
    "//    Names are the variable with dots replaced by underscores. w true is AV; every other point is AI. Units are No-Units.,,,,,,,,",
    "//    Poll 10771 length 90 includes 10860. On sprtp 1.8.5 that read gets no valid reply so DA_U16_03 does not update.,,,,,,,,",
    "//    Reads after 10510 are one address early on that server. Writes are not. Moves use the register the JSON names.,,,,,,,,",
    "//,,,,,,,,",
    "," * 8,
    "," * 8,
]
lines += banner("Data Arrays")
lines += [
    "," * 8,
    "Data_Arrays,,,,,,,,",
    "Data_Array_Name , Data_Format , Data_Array_Length,,,,,,",
]
for block in range(nblocks):
    lines.append(
        f"DA_U16_{block:02d}_$node_id , Uint16 , {ARRAY_LEN},,,,,,"
    )
    lines.append(
        f"DA_Flt_{block:02d}_$node_id , Float , {ARRAY_LEN},,,,,,"
    )
lines.append("," * 8)
lines += banner("Client Side Nodes")
lines += [
    "," * 8,
    "Nodes,,,,,,,,",
    "Node_Name , Node_ID , Protocol , Adapter , IP_Address , Address_Type , Modbus_TCP_IP_Port,,",
    "Dev_$node_id , $node_id , Modbus/TCP , N1 , $ip_address , ADU , 50502,,",
    "," * 8,
]
lines += banner("Client Side Map Descriptors")
lines += [
    "," * 8,
    "Map_Descriptors,,,,,,,,",
    "Map_Descriptor_Name , Data_Array_Name , Data_Array_Offset , Function , Node_Name , Data_Type , Address , Length , Scan_Interval",
]
for poll in polls:
    lines.append(
        f"{poll['name']} , {poll['arr']} , {poll['off']} , Rdbc , Dev_$node_id , FC03 , {poll['addr']} , {poll['length']} , 1.000s"
    )
lines.append("," * 8)
lines += banner("Moves")
lines += [
    "," * 8,
    "Moves,,,,,,,,",
    "Source_Data_Array , Source_Offset , Target_Data_Array , Target_Offset , Length , Function , Source_Low_Scale , Source_High_Scale , Target_Low_Scale",
]
for move in moves:
    lines.append(
        f"{move['src_arr']} , {move['src_off']} , {move['dst_arr']} , {move['dst_off']} , 1 , {move['function']} , 0 , 1 , 0"
    )
lines.append("," * 8)
lines += banner("Server Side Nodes")
lines += [
    "," * 8,
    "Nodes,,,,,,,,",
    "Node_Name , Node_ID , Protocol , Node_Option,,,,,",
    "MCPLA_$node_id , <$node_offset+$node_id> , BACnet_IP , $bac_cov_option,,,,,",
    "," * 8,
]
lines += banner("Server Side Map Descriptors")
lines += [
    "," * 8,
    "Map_Descriptors,,,,,,,,",
    "Map_Descriptor_Name , Data_Array_Name , Data_Array_Offset , Function , Node_Name , Data_Type , Object_ID , Units,",
]
for point in points:
    index = point["index"]
    dst_block = index // BLOCK
    lines.append(
        f"{point['name']} , DA_Flt_{dst_block:02d}_$node_id , {index} , Server , MCPLA_$node_id , {point['bac']} , {point['oid']} , No-Units,"
    )

text = "\n".join(lines) + "\n"
if "Join_Float_Swapped" in text:
    die("refusing to write Join_Float_Swapped")

tmp = out + ".tmp"
with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(text)
os.replace(tmp, out)
print(
    f"msa-gateway: {len(points)} points ({n_join} Join_Float, {n_scale} Scale), "
    f"{nblocks} polls {BASE}-{END}, wrote {out}",
    file=sys.stderr,
)
PY
