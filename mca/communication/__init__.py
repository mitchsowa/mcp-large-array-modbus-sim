# HARNESS FILE -- trimmed stand-in for the real mca/communication/__init__.py.
#
# Production imports HMI, Rest, MQTTRouter, MemRingBuffer, and the real
# HPCDecoder module. Unit.py (production) now imports ControlCMD and
# HPCDecoder at class-body time (`hpc_parsers = {10: HPCDecoder()}`), so
# those two names have to exist for the Modbus stack to import. The stubs
# below are only enough to construct a Unit; they do not decode HPC packets.
from .ModbusData import ModbusData


class HPCDecoder:
    def __init__(self, *args, **kwargs):
        pass


class ControlCMD:
    def __init__(self, cycle, call, lwt_sp):
        self.cycle = cycle
        self.call = call
        self.lwt_sp = lwt_sp

    def bytes(self) -> bytes:
        return b""


__all__ = ["ModbusData", "ControlCMD", "HPCDecoder"]
