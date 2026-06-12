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
    ./run_sim.py                # faithful: reg 10504 broken as in production
    ./run_sim.py --fix-10504    # config-level overlay so full reads work

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
ids to optoX-sNN. alarm.N/comp.N/sensor.N registers index LEXICOGRAPHICALLY
sorted collections, so swap in real serial/id formats to match a deployed
machine's ordering.

## Findings from running the production files as-is

- Reg 10504 (alarm.value.value) caches None; any read covering it gets no
  response at all (connection-level, not a Modbus exception). Server
  survives. Presents as 'random timeouts' to a BMS polling full blocks.
- running() is inverted via ModbusData.status() (mb_timeout semantics);
  masked in production because the main loop re-calls modbus.start(),
  whose thread.is_alive() guard no-ops.
- Float registers only convert int values; non-integer config floats read
  as 0.0 over Modbus. Defaults (lwt=121 etc.) are ints, so latent.
- MCAConfig list-overlay construction validates after each layer but
  shims only at the end; unused in production (directory merge is one
  layer) but a trap for tooling.
- config/util.py runs logging.basicConfig at import; run_sim uses
  force=True to override.
- state register = base state + status bits (16 modbus, 32 mqtt, 64 web,
  128 alarm); on <-> not config.stop; cut_inout reads cut_in, writes both.
