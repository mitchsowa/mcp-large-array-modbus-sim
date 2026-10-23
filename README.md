# mcp-large-array-modbus-sim -- MCP Large Array Modbus server simulator

Runs the real, unaltered production files on a simulated MCA so a BMS
gateway, HMI, or mbtest.sh can poll TCP 50502 exactly as production serves
it. Set values at the sim> prompt; the gateway sees them on its next poll.

Real production files (byte-identical; fix here, drop back into the
program): modbus/__init__.py, modbus/ModbusServer.py,
mca/communication/ModbusData.py, mca/MCAConfig.py, mca/Util.py,
mca/Const.py, all of mca/components/ (Relay, Sensor, Timer, Unit,
UnitAlarm, UnitStatus, __init__), config/Config.py, config/util.py, and
the resources/config fragment directory.

Harness files (clearly marked in their headers): mca/__init__.py (trimmed
-- the real one imports the whole application), mca/communication/
__init__.py, simmca.py, run_sim.py, selftest.py, mbtest.sh.

## Run

    pip install -r requirements.txt --break-system-packages
    ./run_sim.py                # dev 1.8.4 map, registers 10501-10860
    ./run_sim.py --fix-10504    # overlays 10504 with static.0 (that address
                                #   is the second copy of state on this map)

pymodbus must be ~3.6 (3.6.9 verified): ModbusData.py imports
pymodbus.datastore.store and pymodbus.device, removed in later releases.
tomli is required by the real config loader. Match deployed versions when
known.

Config is a DIRECTORY of numbered fragments merged in filename order,
default resources/config, env MCA_CONFIG honored (same as mca/__main__.py).
Use a RELATIVE path: MCAConfig.load_path raises NameError on absolute
paths (production bug, kept faithful). To mirror a deployed unit, drop its
50_/80_ layer files into resources/config.

Port 50502/all interfaces is hardcoded in ModbusServer.py. Request offset:
pymodbus zero_mode=False means request addr = map addr - 1; mbtest.sh
auto-detects.

## Placeholders pending real-world data (see simmca.py header)

Unit serials default to 6-digit numerics, names to MAC-style hex; sensor
ids to optoX-sNN. alarm1/2/3/l.N, ustatus.N, comp.N, and sensor.N registers
index LEXICOGRAPHICALLY sorted collections, so swap in real serial/id
formats to match a deployed machine's ordering.

## Findings from running the production files as-is

Synced to `upstream/dev` `66bda6b` (config version 1.8.4). The map is
10501-10860: run_enable, a second int copy of state at 10504, mcpalarm,
alarm1/2/3 plus alarml, ustatus, run_backup, a BACnet clock, mcpwarn, and
three relay-state registers. See CLAUDE.md for the address list.

- The old 10504 `alarm.value.value` timeout is gone. `getValues` returns
  -2 for a None cache cell instead of failing the response. A non-digit
  alarm/comp/sensor/ustatus index can still cache None.
- `running()` is `alive and running`. `gateway_status()` (formerly
  `status()`) still reports True when the last poll is older than
  mb_timeout, and `running()` no longer consults it.
- Float registers only convert int values; non-integer config floats read
  as 0.0 over Modbus. Defaults (lwt=121 etc.) are ints, so latent.
- Writes of cut_inout and config floats keep only the high word (low word
  forced to 0) and store int(float). 132.0 round-trips; other values may not.
- `run_enable` is hardcoded 0 in MCA.py. The sim mirrors that.
- MCAConfig list-overlay construction validates after each layer but
  shims only at the end; unused in production (directory merge is one
  layer) but a trap for tooling.
- config/util.py runs logging.basicConfig at import; run_sim uses
  force=True to override.
- state register = base state + status bits (16 modbus, 32 mqtt, 64 web,
  128 alarm), published at both 10503 and 10504; on <-> not config.stop;
  cut_inout reads cut_in, writes both.
