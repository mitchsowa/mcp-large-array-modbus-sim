import logging
from enum import Flag, auto

from mca.components import Unit


# strucutres to use to interpret alarm bits
# not functional yet
# Warning Alarms: has a 2s timer before tripping plc code
class Reg1(Flag):
    # Reg1
    HP_Alarm = auto()  # 1
    PowerFault_Alarm = auto()  # 2
    Cond_Flow_Alarm = auto()  # 4
    Evap_Flow_Alarm = auto()  # 8
    Modbus_Alarm = auto()  # 16
    AOTS_Alarm = auto()  # 32
    Defrost_Alarm = auto()  # 64
    EStop_Alarm = auto()  # 128
    Amb_Range_Alarm = auto()  # 256
    Cond_frzpro2_Alarm = auto()  # 512
    Evap_frzpro2_Alarm = auto()  # 1024
    LP_Alarm = auto()  # 2048
    High_LWT_Alarm = auto()  # 4096
    UNUSED13 = auto()  # 8192
    Sensor_Alarm = auto()  # 16384
    Lockout_Alarm = auto()  # 32768 ignore in display


# Lockout Alarms: trips after 5s in plc code
class Reg2(Flag):
    # reg2
    HP_LCK_Alarm = auto()
    PowerFault_LCK_Alarm = auto()
    Cond_Flow_LCK_Alarm = auto()
    Evap_Flow_LCK_Alarm = auto()
    OPSS_LCK_Alarm = auto()
    LP_LCK_Alarm = auto()
    PDS_LCK_Alarm = auto()
    Defrost_LCK_Alarm = auto()
    MPM_LCK_Alarm = auto()
    Local_Stop_LCK_Alarm = auto()
    UNUSED10 = auto()
    UNUSED11 = auto()
    UNUSED12 = auto()
    UNUSED13 = auto()
    UNUSED14 = auto()
    UNUSED15 = auto()


# sensor Alarms: trips after 5s in plc code
class Reg3(Flag):
    # reg 3
    Tank_Probe_CLD_Alarm = auto()
    Tank_Probe_HOT_Alarm = auto()
    Cond_LWT_Probe_Alarm = auto()
    Cond_EWT_Probe_Alarm = auto()
    Evap_Probe_Alarm = auto()
    Amb_Air_Probe_Alarm = auto()
    SLT_Probe_Alarm = auto()
    HP_Sensor_Alarm = auto()
    LP_Sensor_Alarm = auto()
    Flow_Meter_Alarm = auto()
    UNUSED10 = auto()
    UNUSED11 = auto()
    UNUSED12 = auto()
    UNUSED13 = auto()
    UNUSED14 = auto()
    UNUSED15 = auto()


class LocalAlarm(Flag):
    # 1 = unit has different config than the config being sent via mqtt and hasn't updated
    SYNC_FAULT = auto()  # 1
    # comp failed to start before timeout after being called
    RUN_TIMEOUT = auto()  # 2
    # run not enabled
    UNIT_OUT_OF_SERVICE = auto()
    # comp has failed to start multiple times
    MULTIPLE_RUN_TIMEOUTS = auto()
    # uit has reached max run timeout
    MAX_RUN_TIMEOUT = auto()
    # unit is disconnected
    DISCONNECT = auto()  # 1 = disconnected
    # 16 = unit not registered. ( no hello message, but sending ctl msgs ))
    NOT_REGISTERED = auto()
    # unit mqtt malformated
    UPDATE_FAULT = auto()


class UnitAlarm:
    @staticmethod
    def JSON(alarm):
        return alarm.__serialize__()

    @staticmethod
    def serialize(alarm):
        return alarm.__serialize__()

    @staticmethod
    def serialize_config() -> dict:
        ret: dict = {}
        for reg in [Reg1, Reg2, Reg3, LocalAlarm]:
            tmp: dict = {"name": {}, "value": {}}
            for member in reg:
                tmp["name"][member.name] = member.value
                tmp["value"][member.value] = member.name
                if reg.__class__ == Reg1:
                    tmp["warn"] = False
                else:
                    tmp["warn"] = True

            ret[reg.__name__] = tmp
        return {"alarms": ret, "hard": ["MULTIPLE_RUN_TIMEOUTS"]}

    # we are passing the alarm state to the unit, then we can just have the unit update its own alarm state based on the modbus registers.
    def __init__(
        self,
        state: list[Reg1 | Reg2 | Reg3] = [Reg1(0), Reg2(0), Reg3(0)],
        localAlarm: LocalAlarm = LocalAlarm(0),
    ):
        self.log = logging.getLogger(__name__)
        self.state = state
        self.localAlarm = localAlarm

    @property
    def reg1(self) -> Reg1 | Reg2 | Reg3:
        return self.state[0]

    @property
    def reg2(self) -> Reg1 | Reg2 | Reg3:
        return self.state[1]

    @property
    def reg3(self) -> Reg1 | Reg2 | Reg3:
        return self.state[2]

    @property
    def names(self) -> list[str]:
        ret: list[str] = [
            name
            for name, member in LocalAlarm.__members__.items()
            if member & self.localAlarm
        ]
        if self.reg1 is not None:
            ret += [name for name, member in Reg1.__members__.items() if member]
        if self.reg2 is not None:
            ret += [name for name, member in Reg2.__members__.items() if member]
        if self.reg3 is not None:
            ret += [name for name, member in Reg3.__members__.items() if member]

        return ret

    @property
    def active_names(self) -> list[str]:
        return (
            self.active_local_names
            + self.active_reg1_names
            + self.active_reg2_names
            + self.active_reg3_names
        )

    @property
    def active_local_names(self):
        return [
            name
            for name, member in LocalAlarm.__members__.items()
            if member & self.localAlarm
        ]

    @property
    def active_reg1_names(self):
        if self.reg1 is not None:
            return [
                name
                for name, member in Reg1.__members__.items()
                if member & self.reg1  # pyright: ignore
            ]
        return []

    @property
    def active_reg2_names(self):
        if self.reg2 is not None:
            return [
                name
                for name, member in Reg2.__members__.items()
                if member & self.reg2  # pyright: ignore
            ]
        return []

    @property
    def active_reg3_names(self):
        if self.reg3 is not None:
            return [
                name
                for name, member in Reg3.__members__.items()
                if member & self.reg3  # pyright: ignore
            ]
        return []

    @property
    def alarm(self):
        return self.reg1.value

    # might be better to return type Enum then convert later
    def modbus_reg1(self) -> int:
        return self.reg1.value

    def modbus_reg2(self) -> int:
        return self.reg2.value

    def modbus_reg3(self) -> int:
        return self.reg3.value

    def modbus_regl(self) -> int:
        return self.localAlarm.value

    def update(self, state: list[int]):
        self.state = [Reg1(state[0]), Reg2(state[1]), Reg3(state[2])]

    def check_local_alarm(self, alarm: LocalAlarm) -> bool:
        return bool(self.localAlarm & alarm)

    def alarmed(self) -> bool:
        if self.reg1 or self.reg2 or self.reg3 or self.localAlarm:
            return True
        return False

    def maint(self, unit: Unit):
        if unit.connected:
            self.unset_alarm("DISCONNECT")
        else:
            self.localAlarm = LocalAlarm["DISCONNECT"]
            return

        if unit.run_timed_out and not self.get_alarm("MULTIPLE_RUN_TIMEOUT"):
            self.set_alarm("RUN_TIMEOUT")
        else:
            self.unset_alarm("RUN_TIMEOUT")

        if unit.sync_timedout:
            self.set_alarm("SYNC_FAULT")
        else:
            self.unset_alarm("SYNC_FAULT")

        if unit.config is not None and unit.config.call_timeout_limit is not None:
            if unit.run_time_out_count > unit.config.call_timeout_limit:
                self.set_alarm("MULTIPLE_RUN_TIMEOUT")
                self.unset_alarm("RUN_TIMEOUT")
            else:
                self.unset_alarm("MULTIPLE_RUN_TIMEOUT")

        if unit.max_run_time_timeout:
            self.set_alarm("MAX_RUN_TIMEOUT")
        else:
            self.unset_alarm("MAX_RUN_TIMEOUT")

        if unit.update_error:
            self.set_alarm("UPDATE_FAULT")
        else:
            self.unset_alarm("UPDATE_FAULT")

        if unit.out_of_service:
            self.set_alarm("UNIT_OUT_OF_SERVICE")
        else:
            self.unset_alarm("UNIT_OUT_OF_SERVICE")

    def set_alarm(self, alarm: str) -> bool:
        if alarm in LocalAlarm.__members__:
            self.localAlarm |= LocalAlarm[alarm]
            return self.get_alarm(alarm)
        else:
            self.log.error("invalid local alarm set")
            return False

    def unset_alarm(self, alarm: str) -> bool:
        if alarm in LocalAlarm.__members__:
            self.localAlarm &= ~LocalAlarm[alarm]
            return not self.get_alarm(alarm)
        else:
            self.log.error("invalid local alarm set")
            return False

    def get_alarm(self, alarm) -> bool:
        if alarm in LocalAlarm.__members__:
            if self.localAlarm & LocalAlarm[alarm]:
                return True
            else:
                return False
        else:
            self.log.error(f"request for invalid local unit alarm {alarm}")
            return False

    def __str__(self) -> str:
        return f"{self.localAlarm} {self.state}"

    def __serialize__(self):
        return {
            "reg1": self.reg1.value,
            "reg2": self.reg2.value,
            "reg3": self.reg3.value,
            "local": self.localAlarm.value,
        }

    def __modbus__(self) -> int:
        return self.reg1.value


###############################################################################

if __name__ == "__main__":
    us = UnitAlarm()
    for reg in [Reg1, Reg2, Reg3, LocalAlarm]:
        print(reg.__name__)
        for member in reg:
            print(f"\t{member.name}->{member.value}")
