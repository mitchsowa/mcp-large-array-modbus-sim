"""
HARNESS FILE -- simulated MCA built from the REAL component classes.

Mirrors the attribute/property semantics of mca/MCA.py that the Modbus
register map touches, verified against upstream/dev (66bda6b, version 1.8.4):

  on            property: int(not config.stop); setter writes config.stop
  run_enable    property: 0, as production hardcodes it
  cut_inout     property: reads config.cut_in; setter writes cut_in AND cut_out
  state         property: _state + status bits (16 modbus, 32 mqtt,
                64 web*hmi, 128 native alarm)
  mcpalarm      property: int(native_alarm.alarm)
  mcpwarn       property: int(native_alarm.warn)
  unit_count    property: len(units)            (config.unit_count is separate)
  num_running_units  property over a settable running set
  run_backup    settable stand-in for controller.run_backup
  year/month/day/hour/minute/second  int(nowdt().X), same as production
  load/source/backup_relay_state  Relay.value.real, 0 when the relay is absent
  units         mca.Util.IDict of REAL Unit objects keyed by id
  sensors       dict[str, REAL Sensor] keyed by "location-name" id

PLACEHOLDERS pending real-world examples from a deployed unit:
  - unit serials: 6-digit numerics "2000NN" (docstring in Unit.py says
    "either a 6 digit number or hp-######"); unit names are MAC-style
    12-hex strings. alarm1.N / comp.N / ustatus.N order follows str(sn) sort.
  - sensor ids: "opto1-sNN" / "opto2-sNN". sensor.N order follows id sort.
Swap these formats for real ones to make register ordering match a
production machine.
"""

from mca.components.Sensor import Sensor
from mca.components.Unit import Unit
from mca.Util import IDict, nowdt


class _RelayBit:
    """stands in for mca.components.Relay: production reads relay.value.real"""

    def __init__(self, value: bool = False):
        self.value = bool(value)


class SimNativeAlarm:
    """stands in for MCANativeAlarmRegister: .alarm and .warn ints.
    mcpalarm / mcpwarn and the state alarm bit read these."""

    def __init__(self, value: int = 0, warn: int = 0):
        self.alarm = int(value)
        self.warn = int(warn)

    def set(self, value: int):
        self.alarm = int(value)

    def set_warn(self, value: int):
        self.warn = int(value)


class SimMCA:
    def __init__(self, config, unit_count: int = 50, sensor_count: int = 14):
        self.config = config
        self._state = 6  # idle per the state table in MCA.py
        self._run_backup = 0

        # status bits composed into the state register, settable via REPL
        self.mb_status = True
        self.mqtt_connected = False
        self.web_status = False
        self.hmi_status = False

        self.alarm = SimNativeAlarm(0)
        self.native_alarm = self.alarm  # MCA exposes both names

        # absent until the REPL (or a test) attaches one; registers then read 0
        self.load_relay = None
        self.source_relay = None
        self.backup_heat_relay = None

        # real Unit objects; sn 6-digit numeric placeholder, name MAC-like
        self.units = IDict()
        for n in range(1, unit_count + 1):
            name = f"AABBCC{n:06X}"
            u = Unit(name=name, config=config, sn=str(200000 + n))
            u.comp_hrs = 100 * n
            self.units[u.id] = u

        # real Sensor objects; id placeholder "optoX-sNN"
        self.sensors = {}
        for n in range(1, sensor_count + 1):
            loc = "opto1" if n <= 7 else "opto2"
            s = Sensor(id=f"{loc}-s{n:02d}", config=config)
            s.update(110 + n)  # plausible tank temps, replace at will
            self.sensors[s.id] = s

        self._running_ids = set(list(self.units.index[:2]))

    # ---- properties mirroring mca/MCA.py ----------------------------------

    @property
    def on(self) -> int:
        a = not self.config.stop
        return int(a.real)

    @on.setter
    def on(self, value):
        self.config.stop = value == 0

    @property
    def run_enable(self) -> int:
        return 0

    @property
    def cut_inout(self):
        return self.config.cut_in

    @cut_inout.setter
    def cut_inout(self, value):
        self.config.cut_in = value
        self.config.cut_out = value

    @property
    def state(self) -> int:
        status = 0
        if self.mb_status is not None:
            status += 16 * self.mb_status.real
        status += (
            (32 * self.mqtt_connected.real)
            + (64 * self.web_status.real * self.hmi_status.real)
            + (128 * bool(self.native_alarm.alarm))
        )
        return self._state + status

    @property
    def mcpalarm(self) -> int:
        return int(self.native_alarm.alarm)

    @property
    def mcpwarn(self) -> int:
        return int(self.native_alarm.warn)

    @property
    def load_relay_state(self) -> int:
        if self.load_relay is not None:
            return self.load_relay.value.real
        else:
            return 0

    @property
    def source_relay_state(self) -> int:
        if self.source_relay is not None:
            return self.source_relay.value.real
        else:
            return 0

    @property
    def backup_relay_state(self) -> int:
        if self.backup_heat_relay is not None:
            return self.backup_heat_relay.value.real
        else:
            return 0

    @property
    def unit_count(self) -> int:
        return len(self.units)

    @property
    def num_running_units(self) -> int:
        return len(self._running_ids)

    @property
    def run_backup(self) -> int:
        return int(self._run_backup)

    @run_backup.setter
    def run_backup(self, value):
        self._run_backup = int(value)

    @property
    def year(self) -> int:
        return int(nowdt().year)

    @property
    def month(self) -> int:
        return int(nowdt().month)

    @property
    def day(self) -> int:
        return int(nowdt().day)

    @property
    def hour(self) -> int:
        return int(nowdt().hour)

    @property
    def minute(self) -> int:
        return int(nowdt().minute)

    @property
    def second(self) -> int:
        return int(nowdt().second)

    # ---- sim helpers -------------------------------------------------------

    def sorted_units(self):
        return sorted(self.units.values(), key=lambda x: str(x.sn))

    def sorted_sensors(self):
        return sorted(self.sensors.values(), key=lambda x: x.id)

    def set_running(self, count: int):
        ordered = [u.id for u in self.sorted_units()]
        self._running_ids = set(ordered[: max(0, min(count, len(ordered)))])

    def attach_relays(self, load=False, source=False, backup=False):
        self.load_relay = _RelayBit(load)
        self.source_relay = _RelayBit(source)
        self.backup_heat_relay = _RelayBit(backup)

    def populate(self):
        """distinct in-range values for every register the harness can set.

        run_enable stays 0 because MCA.run_enable returns 0. static.0 stays 0
        because the map hardcodes that key. Floats are whole numbers because
        updateRegs only splits int values. Clock registers follow the real clock.
        """
        self.on = 1
        self._state = 5
        self.mb_status = True
        self.mqtt_connected = False
        self.web_status = False
        self.hmi_status = False
        self.alarm.set(3)
        self.alarm.set_warn(9)
        self.set_running(17)
        self.config.lwt = 141
        self.config.setpoint = 135
        self.cut_inout = 128
        self.run_backup = 1
        self.attach_relays(load=True, source=False, backup=True)
        self._phase = -1
        self.tick()

        for i, unit in enumerate(self.sorted_units(), start=1):
            unit.comp_hrs = 5000 + i
            unit.alarm.update([1000 + i, 2000 + i, 3000 + i])
            # LocalAlarm only defines the low 8 bits, so the unit number itself
            unit.alarm.localAlarm = type(unit.alarm.localAlarm)(i)
            unit.status = type(unit.status)(100 + i)

    def tick(self):
        """step every tank probe by 1 each call, wrapping after 10."""
        self._phase = getattr(self, "_phase", -1) + 1
        step = self._phase % 10
        for i, sensor in enumerate(self.sorted_sensors(), start=1):
            sensor.update(160 + i + step)
