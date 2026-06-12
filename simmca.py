"""
HARNESS FILE -- simulated MCA built from the REAL component classes.

Mirrors the attribute/property semantics of mca/MCA.py that the Modbus
register map touches, verified against the production source:

  on          property: int(not config.stop); setter writes config.stop
  cut_inout   property: reads config.cut_in; setter writes cut_in AND cut_out
  state       property: _state + status bits (16 modbus, 32 mqtt,
              64 web*hmi, 128 native alarm)
  unit_count  property: len(units)            (config.unit_count is separate)
  num_running_units  property over a settable running set
  units       mca.Util.IDict of REAL Unit objects keyed by id
  sensors     dict[str, REAL Sensor] keyed by "location-name" id
  alarm       object exposing .value.value (register 10504's intended path)

PLACEHOLDERS pending real-world examples from a deployed unit:
  - unit serials: 6-digit numerics "2000NN" (docstring in Unit.py says
    "either a 6 digit number or hp-######"); unit names are MAC-style
    12-hex strings. alarm.N / comp.N order follows str(sn) sort.
  - sensor ids: "opto1-sNN" / "opto2-sNN". sensor.N order follows id sort.
Swap these formats for real ones to make register ordering match a
production machine.
"""

from mca.components.Sensor import Sensor
from mca.components.Unit import Unit
from mca.Util import IDict


class _Enumish:
    def __init__(self, value: int = 0):
        self.value = int(value)


class SimNativeAlarm:
    """stands in for MCANativeAlarmRegister: .alarm int, and .value.value
    so the alarm.value.value path of register 10504 is resolvable"""

    def __init__(self, value: int = 0):
        self.alarm = int(value)
        self.value = _Enumish(value)

    def set(self, value: int):
        self.alarm = int(value)
        self.value = _Enumish(value)


class SimMCA:
    def __init__(self, config, unit_count: int = 50, sensor_count: int = 14):
        self.config = config
        self._state = 6  # idle per the state table in MCA.py

        # status bits composed into the state register, settable via REPL
        self.mb_status = True
        self.mqtt_connected = False
        self.web_status = False
        self.hmi_status = False

        self.alarm = SimNativeAlarm(0)
        self.native_alarm = self.alarm  # MCA exposes both names

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
            status += 16 * bool(self.mb_status).real
        status += (
            (32 * bool(self.mqtt_connected).real)
            + (64 * bool(self.web_status).real * bool(self.hmi_status).real)
            + (128 * bool(self.native_alarm.alarm))
        )
        return self._state + status

    @property
    def unit_count(self) -> int:
        return len(self.units)

    @property
    def num_running_units(self) -> int:
        return len(self._running_ids)

    # ---- sim helpers -------------------------------------------------------

    def sorted_units(self):
        return sorted(self.units.values(), key=lambda x: str(x.sn))

    def sorted_sensors(self):
        return sorted(self.sensors.values(), key=lambda x: x.id)

    def set_running(self, count: int):
        ordered = [u.id for u in self.sorted_units()]
        self._running_ids = set(ordered[: max(0, min(count, len(ordered)))])
