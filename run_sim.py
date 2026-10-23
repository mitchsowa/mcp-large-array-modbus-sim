#!/usr/bin/env python3
"""
run_sim.py -- NWHS Modbus server simulator (integrated build)

Real, unaltered production files: modbus/*, mca/communication/ModbusData.py,
mca/MCAConfig.py, mca/Util.py, mca/Const.py, mca/components/* (all six
classes + __init__), config/Config.py, config/util.py, and the
resources/config fragment directory. Harness files are clearly marked:
mca/__init__.py (trimmed), mca/communication/__init__.py, simmca.py, this
file, selftest.py.

Config loading mirrors production: a DIRECTORY of numbered fragments merged
in filename order (config/util.py:load_configuration), default
resources/config, overridable with MCA_CONFIG -- same env var as
mca/__main__.py. Path must be RELATIVE (MCAConfig.load_path breaks on
absolute paths -- faithful to production).

Register range is derived exactly as mca/MCA.py does:
int(min/max(config.parameters.to_dict().keys())). Cache pump interval
defaults to config loop_freq (ms), like the production main loop.

The map is whatever resources/config/01_modbus.json says (dev 1.8.4:
10501-10860). --fix-10504 still overlays that one address with static.0;
on this map 10504 is the second copy of state, so the overlay masks it.
"""

import argparse
import logging
import os
import sys
import threading

from mca.MCAConfig import MCAConfig
from mca.communication import ModbusData
from modbus import NWHSModbusServer
from simmca import SimMCA

HELP = """commands:
  sensor N V      set sensor N (1-14, id-sorted) value    e.g.  sensor 3 142
  comp N HRS      set unit N (sn-sorted) compressor hours e.g.  comp 2 4511
  alarm N WORD    set unit N alarm1 (Reg1) word          e.g.  alarm 1 5
  running N       set number of running units             e.g.  running 12
  set ATTR V      set MCA attribute/property              e.g.  set on 1 | set cut_inout 132
  state N         set base state value (status bits added automatically)
  flag NAME 0|1   set status bit input: mb_status mqtt_connected web_status hmi_status
  nalarm V        set native alarm (mcpalarm; adds 128 to state when nonzero)
  nwarn V         set native warn (mcpwarn)
  config KEY V    set config value                        e.g.  config lwt 145
  update          refresh the register cache now
  dump            show raw cache contents
  status          show server/data status
  help            this text
  quit            exit
"""


def parse_num(s: str):
    try:
        return int(s)
    except ValueError:
        return float(s)


def main() -> int:
    ap = argparse.ArgumentParser(description="NWHS Modbus server simulator")
    ap.add_argument("-c", "--config", default=os.environ.get("MCA_CONFIG", "resources/config"),
                    help="config DIRECTORY, relative path (default: resources/config, env MCA_CONFIG)")
    ap.add_argument("-n", "--units", type=int, default=50,
                    help="simulated unit count (default: 50, full register map)")
    ap.add_argument("-i", "--interval", type=float, default=None,
                    help="cache pump seconds (default: config loop_freq/1000)")
    ap.add_argument("--log-level", default="WARNING",
                    help="DEBUG/INFO/WARNING/ERROR (default WARNING; INFO logs every read)")
    ap.add_argument("--fix-10504", action="store_true",
                    help="overlay reg 10504 to static.0 (on this map that masks the second state word)")
    ap.add_argument("--port", type=int, default=50502,
                    help="TCP port (default 50502, hardcoded in production MCA.py)")
    ap.add_argument("--populate", action="store_true",
                    help="fill registers with distinct values; sensors step every pump")
    ap.add_argument("--no-repl", action="store_true", help="headless")
    args = ap.parse_args()

    # force=True because config/util.py calls basicConfig at import time
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING),
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
        force=True,
    )

    cfg = MCAConfig(args.config)
    if args.fix_10504:
        cfg.parameters["10504"] = "static.0"

    # mirror mca/MCA.py register-range derivation exactly
    params = cfg.parameters.to_dict().keys()
    start, end = int(min(params)), int(max(params))

    interval = args.interval
    if interval is None:
        lf = cfg.loop_freq or 1000
        interval = float(lf) / 1000.0

    sim = SimMCA(cfg, unit_count=args.units)
    if args.populate:
        sim.populate()

    data = ModbusData(sim, start=start, end=end)

    srv = NWHSModbusServer(data, port=args.port, version=str(cfg.version))
    srv.thread.daemon = True  # external tweak: real run() never exits its loop
    srv.start()

    stop = threading.Event()

    def pump():
        while not stop.is_set():
            try:
                if args.populate:
                    sim.tick()
                data.update()
            except Exception as e:
                print(f"pump error: {e!r}", file=sys.stderr)
            stop.wait(interval)

    threading.Thread(target=pump, daemon=True, name="cache-pump").start()

    print(f"config version {cfg.version}  registers {start}-{end}  "
          f"on 0.0.0.0:{args.port}  ({args.units} units, pump {interval:.1f}s)")

    if args.no_repl:
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return 0

    print("type 'help' for commands\n")
    while True:
        try:
            line = input("sim> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        try:
            cmd, *rest = line.split()
            if cmd in ("quit", "exit"):
                break
            elif cmd == "help":
                print(HELP)
            elif cmd == "sensor":
                n, v = int(rest[0]), parse_num(rest[1])
                s = sim.sorted_sensors()[n - 1]
                s.update(v)
                data.update()
                print(f"{s.id} = {s.value}")
            elif cmd == "comp":
                n, v = int(rest[0]), int(rest[1])
                u = sim.sorted_units()[n - 1]
                u.comp_hrs = v
                data.update()
                print(f"unit sn {u.sn} comp_hrs = {v}")
            elif cmd == "alarm":
                n, v = int(rest[0]), int(rest[1])
                u = sim.sorted_units()[n - 1]
                u.alarm.update([v, 0, 0])
                data.update()
                print(f"unit sn {u.sn} alarm reg1 = {v} ({u.alarm.active_reg1_names})")
            elif cmd == "running":
                sim.set_running(int(rest[0]))
                data.update()
                print(f"num_running_units = {sim.num_running_units}")
            elif cmd == "set":
                attr, v = rest[0], parse_num(rest[1])
                setattr(sim, attr, v)
                data.update()
                print(f"mca.{attr} = {getattr(sim, attr)}")
            elif cmd == "state":
                sim._state = int(rest[0])
                data.update()
                print(f"state register now {sim.state} (base {sim._state} + status bits)")
            elif cmd == "flag":
                setattr(sim, rest[0], bool(int(rest[1])))
                data.update()
                print(f"{rest[0]} = {getattr(sim, rest[0])}  state = {sim.state}")
            elif cmd == "nalarm":
                sim.alarm.set(int(rest[0]))
                data.update()
                print(f"native alarm = {sim.alarm.alarm}  state = {sim.state}")
            elif cmd == "nwarn":
                sim.alarm.set_warn(int(rest[0]))
                data.update()
                print(f"native warn = {sim.alarm.warn}")
            elif cmd == "config":
                key, v = rest[0], parse_num(rest[1])
                cfg[key] = v
                data.update()
                print(f"config.{key} = {cfg.get(key)}")
            elif cmd == "update":
                data.update()
                print("cache refreshed")
            elif cmd == "dump":
                print(data.cache)
            elif cmd == "status":
                print(f"thread alive: {srv.thread.is_alive()}  running(): {srv.running()}  "
                      f"gateway_status(): {data.gateway_status()}  cut_inout: {sim.cut_inout}  on: {sim.on}")
            else:
                print(f"unknown command: {cmd} (try 'help')")
        except (IndexError, ValueError, KeyError, AttributeError) as e:
            print(f"bad arguments: {e!r} (try 'help')")

    stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
