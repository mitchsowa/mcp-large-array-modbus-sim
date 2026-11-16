# CLAUDE.md

MCP Large Array (MCPLA) Modbus server simulator. Runs real, unaltered production files from
the Nyle MCA program on a simulated MCA so a BMS gateway/HMI can poll TCP
50502 exactly as production serves it. Primary use: reproduce Modbus-layer
bugs, fix them here, drop the fixed file back into the main program.

## The one rule that matters: file provenance

Two classes of files, and the distinction is the whole point of this repo:

**Production files (byte-identical to the main program).** Listed in
`PROVENANCE.md5`. These are: `modbus/*`, `mca/communication/ModbusData.py`,
`mca/MCAConfig.py`, `mca/Util.py`, `mca/Const.py`, everything in
`mca/components/`, `config/Config.py`, `config/util.py`, and all of
`resources/config/`. Do NOT modify these for harness convenience, to
silence warnings, to modernize style, or to satisfy newer pymodbus. The
ONLY reason to edit one is when the task is explicitly fixing a production
bug — in that case keep the diff minimal, update `PROVENANCE.md5` in the
same commit (`md5sum <file>` and replace the line), and state in the
commit message that the change must flow back to the main program.

**Harness files (ours, edit freely).** `run_sim.py`, `simmca.py`,
`selftest.py`, `mbtest.sh`, `scripts/*`, `mca/__init__.py` (trimmed — the
real one imports the whole application), `mca/communication/__init__.py`.
Each carries a HARNESS FILE header.

After ANY change run both:

    ./scripts/check-provenance.sh   # verbatim files untouched (or intentionally updated)
    ./scripts/smoke.sh              # boots sim, verifies registers + write path over the wire

To re-pin the production files to the main program:

    git fetch upstream                  # git@github.com:NyleWaterHeatingSystems/mcp-large-array.git
                                        # fetch refspec is refs/heads/sprtp only; push URL is DISABLED
    ./scripts/check-dev-sync.sh         # diffs every PROVENANCE.md5 file vs upstream/sprtp

`check-dev-sync.sh` reads its file list from `PROVENANCE.md5` and maps each
path into the program layout (prefix `src/`, except `resources/...`). On
drift, resync the file (`git show upstream/sprtp:src/<path> > <local path>`),
regenerate the `PROVENANCE.md5` line, update any harness that references
changed/renamed symbols, then re-run smoke. The program keeps source under
`src/`; this repo flattens it to `mca/`, `modbus/`, `config/`.

Current pin: `upstream/sprtp` `ef27516` (2026-11-11), config version 1.8.5.
That branch is the only upstream ref this repo fetches. `check-dev-sync.sh`
compares against `sprtp`.
`Unit.py` imports `ControlCMD` and `HPCDecoder` from `mca.communication`;
the harness `__init__` stubs those two names so a Unit can be constructed.
They do not decode HPC packets.

## Environment constraints (will bite you)

- `pymodbus==3.6.9` required. ModbusData.py imports
  `pymodbus.datastore.store` and `pymodbus.device`, removed in later
  releases. Do not "fix" the imports — that's production code. Install:
  `pip install -r requirements.txt --break-system-packages`.
- `tomli` required by the real config loader.
- Config path may be relative (default `resources/config`, env
  `MCA_CONFIG`). A relative path is joined to the working directory.
  An absolute path is used as given.
- Port 50502 on all interfaces is hardcoded in `ModbusServer.py`.
- Wire offset: pymodbus `zero_mode=False`, so client request address =
  map address - 1 (e.g. read 10500 to get register 10501).

## Run / interact

    ./run_sim.py                # sprtp 1.8.5 map, registers 10501-10860
    ./run_sim.py --fix-10504    # overlays 10504 with static.0; that address
                                #   is the second copy of state on this map
    ./selftest.py [host]        # one-shot BMS-style poll
    ./mbtest.sh -H <host>       # full labeled register dump to screen + log
    ./scripts/msa-gateway.sh [out.csv]
                                # MSA gateway CSV from 03_modbus.json
                                #   (default prof7tb.csv)

REPL: `sensor N V`, `comp N HRS`, `alarm N WORD` (alarm1 / Reg1 flags), `running N`,
`set on 1`, `set cut_inout 132`, `set run_backup 1`, `state N`, `flag mb_status 0|1`,
`nalarm V`, `nwarn V`, `config KEY V`, `update`, `dump`, `status`, `quit`.

## Architecture in one paragraph

`run_sim.py` builds `MCAConfig` from the config directory (numbered
fragments merged in filename order by `config/util.py`), constructs
`SimMCA` (`simmca.py` — real `Unit`/`Sensor`/`UnitAlarm` objects plus
properties mirroring `mca/MCA.py`: `on` ↔ `not config.stop`, `run_enable`
hardcoded 0, `cut_inout` reads `cut_in`/writes both, `state` = base +
status bits 16/32/64/128, `mcpalarm`/`mcpwarn` from the native alarm,
`run_backup` settable, clock fields from `nowdt()`, relay states from
stand-in relay bits), wraps it in the real `ModbusData` (register map =
`config.parameters` from `01_modbus.json`, range 10501–10860), serves it
with the real `NWHSModbusServer` (background thread, private asyncio loop),
and pumps `data.update()` every `loop_freq` ms like the production main loop.
Reads come from the cache; writes go directly to config/MCA.

## Register map (01_modbus.json, sprtp 1.8.5)

10501 on (rich dict, type int) · 10502 run_enable (hardcoded 0) · 10503 state
· 10504 state (second int copy, not a float partner) · 10505 mcpalarm ·
10506 unit_count · 10507 num_running_units · 10508 lwt float pair ·
10510 config.warm_cut_in (no type, published as one int; default 115) ·
10511 still `"float"` · 10512 config.cold_per_warm float pair (default
0.25, so the non-int float bug publishes 0.0) · 10514 num_warm_sensors ·
10515 operational_mode (toml default 2) · 10516 num_raw_cold_sensors ·
10517–10519 static.0 · 10520 cut_inout float pair (writable; the write path
keeps only the high word and forces the low word to 0). Because 10510 emits
one word and 10511 emits none, the cache is one register short and every
read after 10510 is one address early. A read that includes 10860
gets no valid reply, because the missing word is filled with -2 and
pymodbus cannot encode it. Writes still use the map address, so a write to 10520 stores
cut_inout and the next read shows it at 10519. · 10522–10549
sensors 1–14 float pairs · 10550–10599 alarm1.1–50 · 10600–10649 comp.1–50
hours · 10650 run_backup · 10651–10656 clock (year/month/day/hour/minute/
second) · 10657–10706 alarm2.1–50 · 10707–10756 alarm3.1–50 ·
10757–10806 alarml.1–50 · 10807–10856 ustatus.1–50 · 10857 mcpwarn ·
10858 load_relay_state · 10859 source_relay_state · 10860
backup_relay_state. Floats span two registers hi-word-first; the partner
address is mapped `"float"` and skipped. `alarm*.N`/`comp.N`/`ustatus.N`
index LEXICOGRAPHICALLY sorted units (str(sn)); `sensor.N` indexes sensor id.

## Known production bugs (reproduce here before fixing)

1. **Reg 10504 alarm.value.value** — gone on this pin. The address is now
   a second int copy of `state`. `getValues` also turns a `None` cache cell
   into -2, so a `None` no longer drops the TCP response. `updateRegs`
   still plants `None` when an `alarm*`/`comp`/`sensor`/`ustatus` index is
   not a digit.
2. **`running()` no longer ANDs gateway status.** `gateway_status()`
   (was `status()`) still returns True when the last poll is OLDER than
   `mb_timeout`. `NWHSModbusServer.running()` ignores it and returns
   `alive and running`.
3. **Float casts**: `updateRegs` only converts `int` values to float
   pairs; non-integer config floats read 0.0 over Modbus. `cold_per_warm`
   ships as 0.25, so that pair publishes 0.0. `lwt` and `warm_cut_in`
   ship as ints.
4. **`cut_inout` / config writes** keep only the high word and force the
   low word to 0 before `ints_to_754`, then store `int(float)`. A value
   whose float low word is nonzero will not round-trip. 132.0 is
   `0x43040000`, so a write of 132.0 stores 132.
5. **`MCAConfig.shim`**: `self.setppoint` typo; branch unreachable with
   shipped config layers. List-overlay construction validates per-layer
   but shims at the end — a trap for tooling, unused in production.
6. **`load_path`** now keeps an absolute path as given. A relative path is
   still joined to the working directory. `scan_environment` uses
   `str.strip(prefix)` (strips a character set, not the prefix).
   `save_config` writes current and previous together; `reset_config`
   still copies in the backup direction.
7. **10510/10511 cache shift.** `warm_cut_in` has no `"type": "float"`,
   and 10511 is still the float-partner skip. `updateRegs` emits one word
   for those two addresses, so the cache is 359 long instead of 360 and
   every later read is one address early. A read that includes 10860
   fails on the wire. `setValues` still keys off the
   request address. `mb_write` defaults to 1; a false `mb_write` makes
   `setValues` return without storing.

## Placeholders awaiting real-world data

`simmca.py` defaults: unit serials 6-digit numeric ("2000NN"), unit names
MAC-style hex, sensor ids "optoX-sNN". Real deployed formats (and the
50_/80_ config layers from a real unit, plus a production `pip freeze`)
should replace these; ordering of alarm.N/comp.N/sensor.N depends on it.
