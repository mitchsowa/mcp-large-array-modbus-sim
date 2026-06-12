import logging
from typing import List, Optional

from pymodbus.datastore.store import BaseModbusDataBlock
from pymodbus.exceptions import ParameterException

from config.Config import Config
import mca
from mca.MCAConfig import MCAConfig
from mca.Util import float_as_int, ints_to_754, nowts, split_float_32


class ModbusData(BaseModbusDataBlock):
    """
    This class caches data for modbus
    it has several functions
    update() -> triggers a sync from the real data to the cached data, floats are split with their registr and next register
    getValues -> gets data from the cache and sends it to modbus
    setValues -> process write to modbus
    updateRegs -> takes an address and count and returns the data that goes in that addresses registers,
    write_float -> used when an object wants to write a float,
        when a float is updated update the register, grab the params then read the new value and update the source
        TODO: handle partial writes, if value is invalide revert
    """

    def __init__(self, mca_inst, start=0, end=0, logger=logging.getLogger(__name__)):
        self.mca: mca.MCA = mca_inst
        self.config: MCAConfig = mca_inst.config
        self.params = self.config._parameters
        self.start: int = start
        self.end: int = end
        self.cache: List = []
        self.log: logging.Logger = logger
        self.log.debug(f"{self.start} - {self.end} ")
        self.last_call: float = 0
        self.update()

    def gateway_status(self) -> bool:
        if self.last_call:
            if self.config.mb_timeout is not None and self.config.mb_timeout > 0:
                return self.last_call < (nowts() - self.config.mb_timeout)
        return True

    def getValues(self, address, count=1) -> list:
        """
        get value from cache and send via modbus
        """
        self.last_call = nowts()
        ret = []
        ln = len(self.cache)
        for addr in range(address - self.start, address + count - self.start):
            if addr >= ln:
                self.log.error(
                    f"invalid address {addr + self.start}({addr}) in {address} {count} from {self.start} to {self.end} in {ln} {self.cache}"
                )
                # TODO: this is modbus error code, verify encoding and documet better
                ret.append(-2)
            else:
                value = self.cache[addr]
                if value is None:
                    ret.append(-2)
                else:
                    ret.append(value)
        self.log.info(f"Sending {address} {count} {ret}")
        return ret

    def update(self) -> None:
        """update data in cache from mca"""
        self.log.debug(f"updating {self.cache}")
        self.cache = self.updateRegs(self.start, self.end - self.start + 1)
        self.log.info(f"updated {self.print_cache(self.cache)}")

    def print_cache(self, cache) -> str:
        ret = ""
        for addr in range(0, len(cache)):
            ret += f"{addr}({addr + self.start})->{self.cache[addr]} "
        return ret

    def validate(self, address, count):
        self.log.debug(f"validating {address} {count} vs {self.start},{self.end}")
        # count - 1 since last address counts as 1 register
        valid = address >= self.start and address + count - 1 <= self.end
        if not valid:
            self.log.error(
                f"INVALID REQUEST {address} {count} for {self.start} {self.end} {valid} "
            )
        return valid

    def setValues(self, address: int, values: list[int | bool]) -> None:
        """
        gets a list of values to be written as a list and a starting address
        data types are either integers or booleans by default and are converted
        based on paramaters configuration value
        """
        num = 1
        self.log.info(f"setValues {address} {values}")

        # check number of values being set
        if type(values) is list:
            num = len(values)
        else:
            self.log.error(f"invalid values {values}")
            raise ParameterException(f"invalid values to set {values}")

        # look at each address the data will be stored in and use it to
        # interpret how to read the data
        for addr in range(address, address + num):
            key, data_type = self.parseParameters(str(addr))
            self.log.info(
                f"setValues parseParameters a{addr} k{key} d{data_type} v{values}"
            )

            if key is None:
                self.log.error(f"no value for {addr} found in config ")
            elif key.split(".")[0] == "float":
                self.log.info("skip float")
                continue
            elif key.split(".")[0] == "cut_inout":
                upper = values.pop(0)
                lower = 0
                fl = ints_to_754(upper, lower)
                cvt = int(fl)
                self.log.info(f"GOT cut_inout  {upper} {lower} {fl} {cvt}")
                self.mca.cut_inout = cvt

            elif key.split(".")[0] == "config":
                self.log.info(f"setting config {key}")
                # assume float
                upper = values.pop(0)
                lower = 0
                fl = ints_to_754(upper, lower)
                cvt = int(fl)
                key_wo_config = ".".join(key.split(".")[1:])
                self.log.info(f"setting {key} - {key_wo_config} to {values} -> {cvt}")
                self.config[key_wo_config] = cvt
            elif key == "on":
                value = values.pop(0)
                if value == 0:
                    value = True
                else:
                    value = False
                self.log.info(f"setting on  {value} ")
                self.config.rupdate("stop", value)
            else:
                self.log.error(f"invalid write {key} {address} {values}")
                values.pop(0)

    def updateRegs(self, address: int, count=1) -> list:
        """
        get a starting address and number of values to read
        then read the data and interpret it based on the paramaters value
        will return 0 rather than null for undefined values to prevent
        errors
        """
        DEFAULT = 0
        self.log.debug(f"updating cache for  {address} {count}")
        # validate the address is valid and return default if needed
        if not self.validate(address, count):
            self.log.error("invalid return empty")
            return [DEFAULT] * count
        else:
            self.log.debug(f"valid address processing {count} at {address}")
            ret = []
            units = []
            ulen = 0
            sensors = []
            for addr in range(address, address + count):
                val = 0
                key, data_type = self.parseParameters(str(addr))

                if key is None:
                    self.log.debug("no key in config returning None")
                    ret.append(int(val))
                    continue

                self.log.debug(f"key is {key}")
                parts = key.split(".")

                # get value from config
                if parts[0] == "float":
                    continue  # if key is float, then previous value is target for updates
                elif parts[0] == "config":
                    key = ".".join(parts[1:])
                    self.log.debug(f"config key is {key}")
                    val = self.config.get(str(key))
                    if val is None:
                        self.log.error(f"config no value found for {key} in config")
                    else:
                        self.log.debug(
                            f"config found value for {addr} at {key} is {val}"
                        )
                # get values from mca
                elif len(parts) == 1:
                    val = self.mca.__getattribute__(parts[0])
                    if val is None:
                        self.log.error(f"no value found for {key} in self")
                    else:
                        self.log.debug(f"found value for {addr} at {key} is {val}")
                elif (
                    parts[0] == "alarm"
                    or parts[0] == "comp"
                    or parts[0] == "sensor"
                    or parts[0] == "static"
                ):
                    comp = parts[0]

                    id = parts[1]
                    if not id.isdigit():
                        ret.append(None)
                        continue
                    id = int(id) - 1
                    if comp == "comp" or comp == "alarm":
                        if units == []:

                            def un_sort(x):
                                return str(x.sn)

                            units = sorted(self.mca.units.values(), key=un_sort)
                            ulen = len(units)
                            self.log.debug(f"units = {units}")

                        if id >= ulen:
                            if (
                                self.mca.config.unit_count is not None
                                and id > self.mca.config.unit_count
                            ):
                                self.log.debug(f"invalid unit {id}")
                            else:
                                self.log.debug(f"invalid unit id {id}")
                            val = 0
                        elif comp == "comp":
                            val = units[id].comp_hrs
                            self.log.debug(f"COMP HRS {id}  {units[id].comp_hrs}")
                        elif comp == "alarm":
                            val = units[id].alarm.__modbus__()
                        else:
                            self.log.error(f"INVALID {id} {units}")
                            val = None
                    elif comp == "static":
                        val = id + 1
                        self.log.debug(f"static {addr} is {val}")

                    elif comp == "sensor":
                        if sensors == []:

                            def sen_sort(x):
                                return x.id

                            sensors = sorted(self.mca.sensors.values(), key=sen_sort)
                            self.log.debug(f"sorted sensor {sensors}")
                        if id > len(sensors):
                            val = int(0)
                        else:
                            if id >= len(sensors):
                                self.log.warning(
                                    f"access invalid sensor {id} form {sensors}"
                                )
                                val = 0
                            else:
                                val = int(sensors[id].value)

                else:
                    self.log.error(
                        f"Invalid parameters mapping for modbus {addr} to {key}"
                    )

                if data_type == "int":
                    self.log.debug(f"cast to int {val}")
                    val = int(val)  # pyright: ignore
                elif data_type == "float":
                    self.log.debug(f"cast to float {val}")
                    o = val
                    if type(val) is int:
                        tmp = float(val)
                        val = split_float_32(float_as_int(tmp))  # pyright: ignore
                        self.log.debug(f"get value SPLIT {o} -> {tmp} to {val}")
                    else:
                        val = (0, 0)

                else:
                    self.log.warning("default value to None with invalid type")
                    val = None

                if val is None:
                    self.log.warning("no value found default to -1")
                    val = DEFAULT

                if type(val) is tuple:
                    ret.append(val[0])
                    ret.append(val[1])
                else:
                    ret.append(val)

            self.log.info(f"modbus values {ret}")
            if len(ret) != count:
                self.log.warning(
                    f"invalid response length {address} {count} {len(ret)}"
                )
            return ret

    def parseParameters(self, tgt) -> tuple[Optional[str], str]:
        key = None
        data_type = "int"
        mapping = self.config.parameters.get(tgt)
        self.log.debug(f"type {type(mapping)}")
        if type(mapping) is str:
            key = mapping
        elif type(mapping) is dict:
            # validate parameters mapping
            if "key" not in mapping:
                self.log.error(f"no key given for {tgt}")
            else:
                key = mapping["key"]
            # if type isn't int change the type
            if "type" in mapping:
                data_type = mapping["type"]
        elif type(mapping) is Config or str(type(mapping)) == "config.Config.Config":
            key = mapping.key
            if mapping.type is not None:
                data_type = mapping.type
        else:
            self.log.error(f"invalid mapping {type(mapping)} for {tgt}")

        return (key, data_type)

    def getCurrentValue(self, value_key):
        pass

    def __serialize__(self):

        return {
            "time": nowts(),
            "start": self.start,
            "end": self.end,
            "last_call": self.last_call,
            "data_gateway_status": self.gateway_status(),
            "cache": self.print_cache(self.cache),
        }
