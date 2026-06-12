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

    ./run_sim.py                # faithful: reg 10504 broken, as production
    ./run_sim.py --fix-10504    # config-level overlay; full-range reads work
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
reads `cut_in`/writes both, `state` = base + status bits 16/32/64/128),
wraps it in the real `ModbusData` (register map = `config.parameters`
from `01_modbus.json`, range 10501–10649), serves it with the real
`NWHSModbusServer` (background thread, private asyncio loop), and pumps
`data.update()` every `loop_freq` ms like the production main loop.
Reads come from the cache; writes go directly to config/MCA.

## Register map (01_modbus.json)

10501 on · 10502/10503 state · 10504 alarm.value.value (BROKEN, below) ·
10505 unit_count · 10506 num_running_units · 10507/9 lwt/setpoint float
pairs · 10511–10518 reserved zeros · 10519 cut_inout float pair (writable)
· 10521–10548 sensors 1–14 float pairs · 10549–10599 alarm.1–50 Reg1 words
(hole: 10552 reserved) · 10600–10649 comp.1–50 hours. Floats span two
registers hi-word-first; the partner address is mapped `"float"` and
skipped. `alarm.N`/`comp.N`/`sensor.N` index LEXICOGRAPHICALLY sorted
collections (str(sn) / sensor id).

## Known production bugs (reproduce here before fixing)

1. **Reg 10504**: `alarm.value.value` hits the alarm.N branch, non-digit
   index plants `None` in the cache; any read covering it gets NO response
   (connection-level, not a Modbus exception). Server survives. Presents
   as "random timeouts" on full-block polls.
2. **`running()` inverted**: `ModbusData.status()` returns True when the
   last poll is OLDER than mb_timeout; `NWHSModbusServer.running()`
   consumes it as health. Masked in production by the main loop re-calling
   `start()` (no-op via `thread.is_alive()` guard).
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
