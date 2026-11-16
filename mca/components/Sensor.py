import logging
from logging import Logger

from mca.MCAConfig import MCAConfig
from mca.Util import nowts

DEBUG = False


class InvalidSensorId(Exception):
    pass


class Sensor:
    quality_descriptions: dict[int, str] = {  # noqa: RUF012
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
    """
       string descriptors of quality values, dict of quality_value -> string description
    """

    def __init__(
        self,
        id: str,
        config: MCAConfig,
        name: str | None = None,
        location: str | None = None,
        logger: Logger | None = None,
    ):
        """
        represent a sensor on the opto
        id - an id for the sensor
        config - the global config object used to represent the sensor
        name - the name of the sensor on the device it is hosted on
        location - the device hosting the sensor
        logger - logging.logger compliant logger

        """
        if logger is None:
            logger = logging.getLogger(__name__ + "." + str(id))

        self.log = logger

        self.id: str = id
        """ id the sensor is identified by generally name-location"""

        tmp = id.split("-")

        if len(tmp) != 2 and (name is None or location is None):
            self.log.error(f"invalid sensor id {self.id} {name} {location} {tmp}")
            raise InvalidSensorId(
                f"invalid sensor id {self.id} {name} {location} {tmp}"
            )

        self.nan = False
        if name is None:
            self.name: str = tmp[1]
            """name of the sensor on the rio or its purpose"""
        else:
            self.name = name

        if location is None:
            self.location: str = tmp[0]
            """location of the sensor(the rio its connected to)"""
        else:
            self.location = location

        self.value: int = 0
        """the current value of the sensor as an integer"""

        self._status = True
        """
        the health of a senosr True indicates healthy
        can be used to flag a sensor as unhealthy in future updates
        """

        self._cold = False
        """indicates if the sensor is considered cold"""

        self.quality: int = -1
        """quality indicator, represents issues with sensor quality may differ per sensor type"""

        self.config = config
        """reference to mca config object"""

        self.last_msg: float = 0.0
        """float of epoch timestamp last message was received"""

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
        """maintainance function currently checks for timeout"""
        if self.timedout:
            self.quality = -2
        return True

    @property
    def timedout(self) -> bool:
        """returns if the sensor has timed out"""
        return nowts() - self.config.sensor_timeout > self.last_msg

    def update(self, value: float):
        """update value of sensor based on received data"""

        if (
            value is None or value != value  # noqa: PLR0124
        ):  # check for weird values by compareing to self
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
    def satisfied(self) -> bool:
        return self.value >= int(self.config.cut_out)

    @property
    def warm(self):
        if not self.status:
            return False

        # only change value if sensor is below cut in or above cut out
        # prioritize cut in to prevent issue with misconfiguration
        if self.value < int(self.config.warm_cut_in):
            self._cold = True
        elif self.value >= int(self.config.cut_out):
            self._cold = False

        # if sensor is not healthy return False
        if self.status:
            return self._cold
        else:
            return False

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
        """pulls the current quality description string from the quality_descriptions dict"""
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
