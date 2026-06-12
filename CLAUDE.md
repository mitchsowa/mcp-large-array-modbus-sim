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

To re-pin the production files to the latest main-program dev branch:

    git fetch upstream                  # git@github.com:NyleWaterHeatingSystems/mcp-large-array.git
    ./scripts/check-dev-sync.sh         # diffs every PROVENANCE.md5 file vs upstream/dev

`check-dev-sync.sh` reads its file list from `PROVENANCE.md5` and maps each
path into the program layout (prefix `src/`, except `resources/...`). On
drift, resync the file (`git show upstream/dev:src/<path> > <local path>`),
regenerate the `PROVENANCE.md5` line, update any harness that references
changed/renamed symbols, then re-run smoke. The program keeps source under
`src/`; this repo flattens it to `mca/`, `modbus/`, `config/`.

## Environment constraints (will bite you)

- `pymodbus==3.6.9` required. ModbusData.py imports
  `pymodbus.datastore.store` and `pymodbus.device`, removed in later
  releases. Do not "fix" the imports — that's production code. Install:
  `pip install -r requirements.txt --break-system-packages`.
- `tomli` required by the real config loader.
- Config path must be RELATIVE (default `resources/config`, env
  `MCA_CONFIG`). `MCAConfig.load_path` raises NameError on absolute paths
  — production bug, kept faithful.
- Port 50502 on all interfaces is hardcoded in `ModbusServer.py`.
- Wire offset: pymodbus `zero_mode=False`, so client request address =
  map address - 1 (e.g. read 10500 to get register 10501).

## Run / interact

    ./run_sim.py                # serves the current dev map (rc28+)
    ./run_sim.py --fix-10504    # legacy: overlays 10504->static.0. Obsolete
                                #   since dev rc28 remapped 10504 to mcpalarm
                                #   (see fixed bug 1); harmless, masks mcpalarm.
    ./selftest.py [host]        # one-shot BMS-style poll
    ./mbtest.sh -H <host>       # full labeled register dump to screen + log

REPL: `sensor N V`, `comp N HRS`, `alarm N WORD` (Reg1 flags), `running N`,
`set on 1`, `set cut_inout 132`, `state N`, `flag mb_status 0|1`,
`nalarm V`, `config KEY V`, `update`, `dump`, `status`, `quit`.

## Architecture in one paragraph

`run_sim.py` builds `MCAConfig` from the config directory (numbered
fragments merged in filename order by `config/util.py`), constructs
`SimMCA` (`simmca.py` — real `Unit`/`Sensor`/`UnitAlarm` objects plus
properties mirroring `mca/MCA.py`: `on` ↔ `not config.stop`, `cut_inout`
reads `cut_in`/writes both, `state` = base + status bits 16/32/64/128,
plus `mcpalarm` and the BACnet clock regs `year`/`month`/`day`/`hour`/
`minute`/`second` and `run_backup` added on dev rc28), wraps it in the
real `ModbusData` (register map = `config.parameters` from
`01_modbus.json`, range 10501–10656), serves it with the real
`NWHSModbusServer` (background thread, private asyncio loop), and pumps
`data.update()` every `loop_freq` ms like the production main loop.
Reads come from the cache; writes go directly to config/MCA.

## Register map (01_modbus.json)

10501 on · 10502/10503 state · 10504 mcpalarm (was alarm.value.value,
BROKEN; remapped on dev rc28 — see fixed bug 1) · 10505 unit_count · 10506
num_running_units · 10507/9 lwt/setpoint float pairs · 10511–10518 reserved
zeros · 10519 cut_inout float pair (writable) · 10521–10548 sensors 1–14
float pairs · 10549–10599 alarm.1–50 Reg1 words (hole: 10552 reserved) ·
10600–10649 comp.1–50 hours · 10650 run_backup · 10651–10656 BACnet clock
(year/month/day/hour/minute/second, all `int(datetime.now().X)`; added on
dev rc28). Floats span two registers hi-word-first; the partner address is
mapped `"float"` and skipped. `alarm.N`/`comp.N`/`sensor.N` index
LEXICOGRAPHICALLY sorted collections (str(sn) / sensor id).

## Known production bugs (reproduce here before fixing)

Bugs 1 and 2 were FIXED on dev rc28 (`ce6621a`) and are no longer
reproducible at the current sync point. Kept here as history — they
reappear if you sync to a tag/branch older than rc28.

1. **Reg 10504** — FIXED rc28. Was: `alarm.value.value` hits the alarm.N
   branch, non-digit index plants `None` in the cache; any read covering it
   gets NO response (connection-level, not a Modbus exception). Server
   survives. Presented as "random timeouts" on full-block polls. Fix:
   `01_modbus.json` remaps 10504 to `mcpalarm` (`int(native_alarm.alarm)`),
   and `ModbusData.getValues` now returns `-2` for a `None` cell instead of
   serving it raw.
2. **`running()` inverted** — FIXED rc28. Was: `ModbusData.status()`
   returns True when the last poll is OLDER than mb_timeout;
   `NWHSModbusServer.running()` consumed it as health (masked in production
   by the main loop re-calling `start()`, a no-op via `thread.is_alive()`).
   Fix: `running()` now returns `alive and running` — the inverted status
   term is commented out (and `status()` is renamed `gateway_status()`).
3. **Float casts**: `updateRegs` only converts `int` values to float
   pairs; non-integer config floats read 0.0 over Modbus. Latent (shipped
   defaults are ints).
4. **`MCAConfig.shim`**: `self.setppoint` typo; branch unreachable with
   shipped config layers. List-overlay construction validates per-layer
   but shims at the end — a trap for tooling, unused in production.
5. **`reset_config` == `backup_config`** (copy direction); `load_path`
   NameError on absolute paths; `scan_environment` uses `str.strip(prefix)`
   (strips a character set, not the prefix).

## Placeholders awaiting real-world data

`simmca.py` defaults: unit serials 6-digit numeric ("2000NN"), unit names
MAC-style hex, sensor ids "optoX-sNN". Real deployed formats (and the
50_/80_ config layers from a real unit, plus a production `pip freeze`)
should replace these; ordering of alarm.N/comp.N/sensor.N depends on it.
