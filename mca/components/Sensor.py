import logging
from typing import Optional

from mca.MCAConfig import MCAConfig
from mca.Util import nowts

DEBUG = False


class Sensor:
    quality_descriptions: dict[int, str] = {
        -2: "Timeout",
        -1: "Unknown",
        0: "OK",
        4: "All analog inputs Analog input is not in range; firmware cannot determine if above or below range.",
        5: "All analog inputs Analog input above operating limits.",
        6: "All analog inputs Analog input below operating limits.",
        7: "All analog inputs Module isolated field circuitry in reset; part of module firmware to auto-recover field circuitry that may be in an undefined state.",
        8: "All analog inputs and outputs Module failed communication with isolated field circuitry like analog to digital and digital to analog converters.",
        15: "All analog inputs Analog input is 10% above the highest range. Applicable to unipolar (zero and positive values only) and bipolar (can include negative and positive values) signal ranges. To determine the highest range value, see the specification table.",
        16: "All analog inputs Analog input is 10% below the lowest range. Applicable only to bipolar (can include negative and positive values) signal ranges. To determine the lowest range value, see the specification table.",
        18: "All analog outputs Analog output fault.",
        19: "All analog outputs Analog output driver over temperature condition, output may cycle on and off.",
        20: "Field excitation/loop voltage fault",
        23: "Thermocouple input Isolated field compensation circuitry or calculation does not give valid data.",
        30: " Any channel reporting quality Channel not present",
    }

    def __init__(
        self,
        id: str,
        config: MCAConfig,
        name: Optional[str] = None,
        location: Optional[str] = None,
        logger=logging.getLogger(__name__ + "." + str(id)),
    ):
        """
        represent a sensor on the opto
        id - an id for the sensor
        config - the global config object used to represent the sensor
        name - the name of the sensor on the device it is hosted on
        location - the device hosting the sensor
        logger - logging.logger compliant logger

        """

        self.log = logger
        # id the sensor is identified by generally name-location
        self.id = id
        tmp = id.split("-")
        # if value is nan value
        self.nan = False

        if len(tmp) != 2 and (name is None or location is None):
            self.log.error(f"invalid sensor id {self.id} {name} {location} {tmp}")
            Exception("invalid sensor id")

        if name is None:
            self.name = tmp[1]
        elif location is None:
            self.location = tmp[0]

        # the current value of the sensor
        self.value: int = 0
        self._status = True

        # internal tracker for cold state
        self._cold = False

        self.quality: int = -1

        # logger

        # configuration
        self.config = config

        self.last_msg = 0

        self.log.debug(f"created sensor {self.id}")

    def update_quality(self, quality) -> bool:
        """
        4 All analog inputs Analog input is not in range; firmware cannot determine if above or below range.
        5 All analog inputs Analog input above operating limits.
        6 All analog inputs Analog input below operating limits.
        7 All analog inputs Module isolated field circuitry in reset; part of module firmware to auto-recover field circuitry that may be in an undefined state.
        8 All analog inputs and outputs Module failed communication with isolated field circuitry like analog to digital and digital to analog converters.
        15 All analog inputs Analog input is 10% above the highest range. Applicable to unipolar (zero and positive values only) and bipolar (can include negative and positive values) signal ranges. To determine the highest range value, see the specification table.
        16 All analog inputs Analog input is 10% below the lowest range. Applicable only to bipolar (can include negative and positive values) signal ranges. To determine the lowest range value, see the specification table.
        18 All analog outputs Analog output fault.
                • When configured for voltage, indicates the load resistance is too low (that is, the load is drawing too much current to maintain the voltage).
                • When configured for current, indicates very high resistance or possible open circuit.
        19 All analog outputs Analog output driver over temperature condition, output may cycle on and off.
        20 Field excitation/loop voltage fault
            • Switch input, powered
            • ICTD input
            • Thermistor input (for curves: 2252, 3K, 10K type 2, 10K type 3, and Custom)
            • 0–400 kOhm input
        23 • ICTD input
            • Thermocouple input Isolated field compensation circuitry or calculation does not give valid data.
        30 Any channel reporting quality Channel not presen
        """
        self.last_msg = nowts()
        self.quality = int(quality)
        return True

    def maint(self) -> bool:
        if self.timedout:
            self.quality = -2
        return True

    @property
    def timedout(self) -> bool:
        return nowts() - self.config.sensor_timeout > self.last_msg

    def update(self, value: float):
        """update value of sensor based on received data"""

        if value is None or value != value:
            self.nan = True
            value = 0
        else:
            self.nan = False

        self.value = int(value)
        self.last_msg = nowts()
        return True

    @property
    def status(self) -> bool:
        """return if the sensor is healthy"""
        return self._status and not self.nan and self.quality == 0 and not self.timedout

    @property
    def healthy(self) -> bool:
        """return if the sensor is healthy"""
        return self.status

    @property
    def cold(self):
        """check if sensor is cold"""
        if not self.status:
            return False

        # only change value if sensor is below cut in or above cut ou
        if self.value < int(self.config.cut_in):
            self._cold = True
        elif self.value >= int(self.config.cut_out):
            self._cold = False

        # if sensor is not healthy return False
        if self.status:
            return self._cold
        else:
            return False

    def get_quality_desc(self) -> str:
        tgt = int(self.quality)
        if tgt in Sensor.quality_descriptions:
            return str(Sensor.quality_descriptions[tgt])
        else:
            return f"unknown sensor quality value {tgt}"

    def __str__(self) -> str:
        return f"S({self.id} c:{self._cold.real} v:{self.value} s:{self.status.real} n:{self.nan.real} q:{self.quality})"

    def __repr__(self) -> str:
        return self.__str__()

    def __serialize__(self):
        return {
            "id": self.id,
            "quality": self.quality,
            "quality_desc": self.get_quality_desc(),
            "value": self.value,
            "cold": self.cold.real,
            "status": self.status,
            "nan": self.nan.real,
        }
