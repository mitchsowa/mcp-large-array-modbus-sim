# Unit.py
from logging import Logger
import json
import logging
from datetime import datetime
from typing import List, Optional

from mca.components.UnitAlarm import Reg1, UnitAlarm
from mca.components.UnitStatus import UnitStatus
from mca.MCAConfig import MCAConfig
from mca.Util import nowts

log: Logger = logging.getLogger(__name__)

"""
# unit life cycle
hello -> updates -> delete
|event | hello | delete | last_update
| --- | --- | --- |
message received for unit should not exist unless an update is received for a unit in a bad state| False | False | 0|
hello message received | True | False | 0
unit runs normally | True | False | recent
unit set to be deleted | True | True  | recent
delet message has been sent |  False | True | recent


# Deletion

"""


class Unit:
    """
    a representation of a unit in the system a unit is intended to go through a lifecycel
    gets heat calls from MCA, will stop itself if issue is detected but will only start when called
    watches its own health and reports issues
    when called sets call time, when changes set sets out of sync until synced.

    initialization - a unit is created with the last known data
    registration/hello - a hello packet form the unit is processed with metadata about the unit
    update - a unit control packet is receive to update the current state of the unit
    control - control is a 3 step process
        1. a desired value is set representing a wanted change on the unit
        2. control - a control message is sent to the unit to make the update
        3. update - the next update will reflect the contrl message changes if they were applied
        this control process repeats until the unit has reached the desired state. if a unit drifts
        messages are sent to return it to the desired state
    """

    @staticmethod
    def serialize(unit):
        return unit.__serialize__()

    @staticmethod
    def JSON(unit):
        return json.dumps(unit.__serialize__())

    def __init__(
        self,
        name: str,
        config: MCAConfig,
        topic: Optional[str] = None,
        tank: int = 0,
        lwt: int = 0,
        diff: int = 0,
        mac: Optional[List[str]] = None,
        model: Optional[str] = None,
        sn: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        the representation of a unit for mcp
        name - the name of the unit, a string of the mac concatinated
        topic - the topic the unit communicates on
        tank - the tank setpoint for the unit
        lwt - the lwt for the unit
        diff - the diff for the unit
        mac - the mac address of the unit
        model - the model of the unit
        sn - the serial number of the unit
        """

        self.ctl_topic = topic if topic is not None else name
        """topic used to send message to unit"""

        self.config: MCAConfig = config
        """config used by the unit"""

        self.id: str = str(name)
        """globally unique id of the unit (mac concatinated)"""

        self.name: str = str(name)
        """name of the unit, mac concatinated"""

        self.status = UnitStatus(0)

        self.ctl_topic = topic
        """topic to send control signals to"""

        self.sn: str = str(sn) if sn is not None else str(name)
        """serial number of the uni either a 6 digit number or hp-######"""

        self.log = (
            logger if logger is not None else logging.getLogger(__name__ + "." + name)
        )
        """logger for instance"""

        self.mac = mac if mac is not None else []
        """mac address in list with 2 char str's list[char(2)]"""

        self.model = model
        """unit model reported by unit"""

        self.alarm = UnitAlarm()
        """unit alarm representation """

        self.master = False
        """the master heatcall bit on the unit"""

        self.standby = False
        """the standby bit on the unit indicating that the unit isn't running for heatcall"""

        self.holding = False
        """the holding register meaning the unit has water that is too hot"""

        self.manual = False
        """if heat call is from manual call"""

        self.cycle: bool = False
        """unit cycle register"""

        self.local_stop: bool = False
        """if the local stop bit is set on the unit"""

        self.cant_run = False
        """cant run bit indicates unit should not be able to respond to heat call"""

        self.comp_state = False
        """wetehr or not the compressor is running"""

        self.cond_state = False
        """wether or not the condenser is running"""

        self.evap_state: Optional[bool] = None
        """wether or not the evap is running"""

        self.comp_hrs: int = 0
        """run hours on the compressor"""

        self.dlp: Optional[float] = None
        """discharge line pressue"""

        self.slp: Optional[float] = None

        self.ewt = 0
        """ entering water temperature"""

        self.lwt = 0
        """the current reported leaving water temperature"""

        self.gpm = 0
        """gpm flow rate through condenser"""

        self.lwt_sp = 0
        """the current reported  desired leaving water temperature"""

        self.diff = 0
        """differential value"""

        self.tank_sp = 0
        """the current reported tank setpoint"""

        # time on unit
        self.time = datetime.fromtimestamp(0)

        """the current time set on the unit"""

        self.ctd = -1
        """value of ctd timer"""

        ###
        # controll values
        ###
        self.hello = False
        """if the unit has been heard from and regiestered"""

        # has message been sent to set unit to appropriate state
        self.update_sent = False
        """if the unit has sent since being changed set in MCA.py"""

        self.sync_timedout = False
        """ if the unit is communicating but isn't synced"""

        # time unit was called to run
        self.call_time: float = 0
        """the last time we requested a heatcall from the unit 0 for no call
        gets set when we first decide to start the unit
        gets reset after we are no longer calling the unit and the unit has stopped
        if another call is initiated before the call is actually stopped its considered
        the same call
        """

        self.run_time_out_count = 0
        """number of times a call has timed out since the last successful call """

        self.max_run_time_timeout = False
        """if set to true we have exceeded max run time"""

        self.last_update_sent = 0
        """the last update that was sent to the unit"""

        # last message from unit
        self.last_update: float = 0
        """ the last time we heard from the unit"""

        self.last_synced: float = 0
        """The last time the unit's reported values matched the desired values"""

        self.started = False
        """
            if the unit started its compressor during the current heatcall,
            set to false when a heat call ends and the unit stops running
            set to true when the compressor starts on a called unit

        """

        self.run_timed_out = False
        """ if we called a unit but it didn't make heat in a given time"""

        self._desired_cycle = True
        """
            local cycle stop in case needed for future use
            both config.stop must be false and _desired_cycle  must be true
            for the unit to be in cycle
        """

        self.update_error = False
        """tracks failed update"""

        self.desired_heatcall = False
        """the desired heatcall state"""

        self._desired_tank = tank
        """desired tank display temperature"""

        self._desired_lwt = lwt
        """the desired lwt value for the unit"""

        self._desired_diff = diff
        """the desired diff value """

        self.deleted = False
        """if the unit is set to be delted"""

        self.log.info(f"created unit {self.id}")

    @property
    def has_local_issues(self) -> bool:
        return self.local_status > 0

    @property
    def max_run_time(self):
        if self.config is not None:
            if self.config.unit_max_run_time is not None:
                return self.config.unit_max_run_time
        self.log.error("unit_max_run_time not found")
        return 64800

    # self.comp_state
    # self.starting

    @property
    def starting(self) -> bool:
        """if the unit has been called and has acked the call but hasn't
        reached compressor start yet"""
        return self.heatcall and not self.running and not self.started

    @property
    def called(self) -> bool:
        return self.desired_heatcall

    @property
    def calling(self) -> bool:
        return self.desired_heatcall and not self.heatcall

    @property
    def running(self) -> bool:
        """the unit is fired and making heat"""
        return self.comp_state

    @property
    def heatcall(self) -> bool:
        """the unit is in heatcall, one of the hc registers is true, it has received the heatcall but may not be started yet"""
        return (
            self.cycle
            and not self.cant_run
            and (self.master or self.holding or self.standby)
        )
        # return self.master or self.holding or self.standby

    @property
    def lockout(self) -> bool:
        return Reg1.Lockout_Alarm & self.alarm.reg1  # pyright: ignore

    @property
    def connected(self) -> bool:
        """
        if the unit is connected determined if it has been
        atleast $time_out_delay since last message from unit
        """
        # return rather last_update time is within the last 2 minutes
        late_time = nowts() - self.time_out_delay
        time_out: bool = self.last_update > late_time
        return time_out

    @property
    def healthy(self) -> bool:
        return (
            not self.cant_run
            and not self.alarmed
            and not self.cant_run
            and self.connected
        )

    @property
    def force_run(self):
        return self.force_run_time > nowts()

    @property
    def time_out_delay(self) -> int:
        """
        the amount of time we can not hear from the unit before
        it is considered timed out in seconds
        """
        if self.config is not None and self.config.unit_timeout is not None:
            delay = self.config.unit_timeout
        else:
            delay = 120
        return delay

    @property
    def alarmed(self) -> bool:
        """returns true if any alarms are present"""
        return self.alarm.alarmed()

    @property
    def nick(self) -> str:
        """returns value for nick name of unit"""

        if self.config is not None:
            if self.config.unit_names is not None:
                if self.config.unit_names.get(self.name) is not None:
                    return str(self.config.unit_names.get(self.name))
        return str(self.sn)

    @property
    def run_time_out_delay(self) -> int:
        """int: number of seconds to wait for unit to run after call"""
        if self.config is not None:
            if self.config.unit_run_timeout is not None:
                return int(self.config.unit_run_timeout)
        return 1200

    @property
    def force_run_time(self) -> float:
        if self.config is not None:
            ret = self.config.rget(f"force_run.{self.name}")
            if ret is not None:
                return float(ret)
            else:
                return 0.0
        else:
            return 0.0

    @property
    def out_of_service(self):
        return not self.enable_run

    @property
    def enable_run(self) -> bool:
        """allow the unit to run, if false, the unit will not run under any circumstances"""
        if self.config is not None:
            val = self.config.rget(f"enable_run.{self.name}")
            if val is None:
                return True
            else:
                return bool(val)
        else:
            return False

    @property
    def local_alarmed(self) -> bool:
        return self.alarm.localAlarm.value > 0

    @property
    def local_status(self) -> int:
        return int(self.status.value)

    @property
    def call_duration(self):
        if self.call_time > 0:
            return nowts() - self.call_time
        else:
            return 0

    @property
    def desired_tank(self) -> int:
        if self.config is not None and self.config.setpoint is not None:
            return self.config.setpoint
        else:
            self.log.error("config doesn't contain setpoint")
            return self._desired_tank

    @property
    def desired_lwt_sp(self) -> int:
        if self.config is not None and self.config.lwt is not None:
            return self.config.lwt
        else:
            self.log.error("config doesn't contain lwt")
            return self._desired_lwt

    @property
    def desired_diff(self) -> int:
        if self.config is not None and self.config.differential is not None:
            return self.config.differential
        else:
            self.log.error("config doesn't contain diff")
            return self._desired_diff

    @property
    def desired_cycle(self) -> int:
        if self.config is not None and self.config.stop is not None:
            return not self.config.stop and self._desired_cycle
        else:
            self.log.error("config doesn't contain setpoint")
            return False

    @property
    def synced(self):
        """returns if the unit is in sync(conncted, update has been sent and state matches current state)
        if a unit is disconnected it is considered synced
        """
        return not self.connected or (
            self.update_sent and self.desired_state == self.current_state
        )

    @property
    def desired_state(self) -> dict:
        """generate json of desired state of unit update values based on config values"""
        # {"heat_call": False,
        # "cycle": False,
        # "sp": {"tank": 0, "lwt": 0, "dif": 0},}

        # extra saftey to prevent run without out_of_service
        return {
            "heat_call": self.enable_run and self.desired_heatcall,
            # this is a fancy way to only show cycle if it is valid and skip it otherwise
            "cycle": self.desired_cycle,
            "sp": {
                "tank": self.desired_tank,
                "lwt": self.desired_lwt_sp,
                "dif": self.desired_diff,
            },
        }

    @property
    def current_state(self) -> dict:
        """generate current state to compare to desired state"""
        return {
            "heat_call": self.heatcall,
            # this is a fancy way to only show cycle if it is valid and skip it otherwise
            **(
                {
                    "cycle": self.cycle,
                }
                if self.cycle is not None
                else {"cycle": self.desired_cycle}
            ),
            "sp": {
                "tank": self.tank_sp,
                "lwt": self.lwt_sp,
                "dif": self.diff,
            },
        }

    def end_force_run(self):
        self.config.rupdate(f"force_run.{self.id}", 0)

    def notify_update_sent(self):
        """function to inform unit its most recent state has been sent to mqtt"""
        self.last_update_sent = nowts()
        self.update_sent = True

    def notify_update_failed(self):
        self.update_sent = False

    def notify_delete_sent(self):
        self.hello = False

    def notify_delete_failed(self):
        pass

    def run(self, manual=False) -> bool:
        """
        requests to start unit ant marks time and that unit is no longer in sync
        manual - bool - if the run is a manual run should only be set to true by mca in manual mode
        returns - if the run call was added successfully, this doesn't mean the unit has responded
        """
        self.manual = manual
        # if run is disabled or its a manual run that has timed out stop the unit
        #
        if (
            not self.enable_run  # run disabled
        ):
            self.log.info(f"{self.id} enable_run false")
            self.stop()
            return False
        elif self.manual and not self.force_run:
            self.log.info("force run is on during manual call")
            self.stop()
            return False
        elif self.max_run_time_timeout:  # enforce max run time
            self.log.info("max run time")
            self.stop()
            return False
        elif self.run_timed_out:
            self.log.info("run time timeout")
            self.stop()
            return False
        elif not self.connected:
            self.log.info("disconnected stopping")
            self.stop()
            return False

        # if we're changing from not running to running update syhnc tracking logic
        if not self.desired_heatcall:
            self.update_sent = False
            self.call_time = nowts()
            if not self.heatcall:
                # if the unit isn't running and we're placing a new heatcall reset started
                self.started = False
            self.desired_heatcall = True

        return self.desired_heatcall

    def stop(self):
        """stops the unit"""
        self.manual = False

        # if we're running and calling desired heatcall
        if self.desired_heatcall:
            self.update_sent = False
            self.desired_heatcall = False

    def off(self):
        """sets unit cycle to off if unit is off we can't turn it back on"""
        self.stop()
        self._desired_cycle = False

    def register(self, obj) -> bool:
        """register new unit to system"""
        self.last_synced = nowts()
        try:
            date = obj["time"]
            if len("%i" % date[0]) == 2:
                # fix 2 digit years
                date[0] = date[0] + 2000
            self.time = datetime(
                year=date[0],
                month=date[1],
                day=date[2],
                hour=date[3],
                minute=date[4],
                second=date[5],
            )
            self.mac = obj["mac"]
            self.model = str(obj["Unit Model"])
            self.sn = str(obj["Unit SN"])
            self.hello = True
        except Exception as e:
            self.log.error(f"unit update error  {self.id} {e} {obj}")
            self.hello = False
        self.log.info(f"UNIT: Registered: {self.id} {self.time}  ")
        return self.hello

    # read attribute message
    def update(self, obj: dict) -> bool:
        """set the unit state to given message
                return - if state was successfully applied
        ctl packet
           {"hc_status": [
           "Boolean M7000", "Boolean M7001", "Boolean M7002"
           ],
            "cant_run": "Boolean M7003",
            "comp": {
            "state": "Boolean M7004",
            "hrs": "Word D7005",
            "dlp": "Word D7030",
            "slp": "Word D7031",
            "ctd": "Word D10102"},
            "cond": {"ewt": "Word D7000",
                "lwt": "Word D7001",
                "gpm": "Float D7006",
                "pump": "Boolean M7005"},
            "setpoints": {"cond_lwt_sp": "Word D7002",
                "tank_storage_sp": "Word D7003",
                "demand_diff_sp": "Word D7004"},
            "ts": ["Word D7012", "Word D7013", "Word D7014", "Word D7015"],
            "alarm": ["Word D7019", "Word D7020", "Word D7021"],
            "evap": {"call": "Boolean M701},
            "cycle": "Boolean M0002",
            "local_stop": "Boolean M0031"}
        """
        if not self.hello:
            self.log.warning(f"missing hello from {self.name}")
            self.update_error = True
            return False

        try:
            self.master, self.standby, self.holding = obj["hc_status"]
            if "cycle" in obj:
                self.cycle = obj["cycle"]
            else:
                self.cycle = None

            if "local_stop" in obj:
                self.local_stop = obj["local_stop"]
            self.cant_run = obj["cant_run"]  # does not account for holding
            comp = obj["comp"]

            self.comp_state = comp["state"]
            self.comp_hrs = comp["hrs"]

            if "ctd" in comp:
                self.ctd = comp["ctd"]
            if "dlp" in comp:
                self.dlp = comp["dlp"]
            if "slp" in comp:
                self.slp = comp["slp"]

            cond = obj["cond"]
            self.ewt = cond["ewt"]
            if "lwt" in cond:
                self.lwt = cond["lwt"]
            self.gpm = cond["gpm"]
            self.cond_state = cond["pump"]

            sp = obj["setpoints"]
            self.lwt_sp = sp["cond_lwt_sp"]
            self.tank_sp = sp["tank_storage_sp"]
            self.diff = sp["demand_diff_sp"]

            if "evap" in obj:
                evap = obj["evap"]
                if "call" in evap:
                    self.evap_state = evap["call"]

            self.update_ts(obj["ts"])

            self.alarm.update(obj["alarm"])

            self.last_update = nowts()
            self.update_error = False
            return True
        except (KeyError, TypeError, ValueError) as e:
            self.log.error("UNIT: invalid update payload on %s with %s", self.name, obj)
            self.log.error(e)
            self.update_error = True
        except Exception as e:
            self.log.error(f"UNIT: update exception {self.name} {e} {obj}")
            self.update_error = True

        return False

    def update_ts(self, ts):
        if self.time.day != ts[0]:
            today = datetime.now()
            self.log.info(f"UNIT: day rollerver on {self.id} got {ts} on {today} ")
            try:
                self.time.replace(
                    year=today.year,
                    month=today.month,
                    day=ts[0],
                    hour=ts[1],
                    minute=ts[2],
                    second=ts[3],
                )
            except Exception as e:
                self.log.error(f"update_ts on {self.id} {ts} {e} ")
                self.time = self.time.replace(
                    day=ts[0], hour=ts[1], minute=ts[2], second=ts[3]
                )

        else:
            self.time = self.time.replace(
                day=ts[0], hour=ts[1], minute=ts[2], second=ts[3]
            )

    def post_heatcall_reset(self):
        """
        resets values after heatcall also runs post_heatdemand_reset
        """
        # called after a heatcall has finished successfually or not
        # unit must be stopped and not be called
        self.max_run_time_timeout = False
        self.call_time = 0
        self.run_timed_out = False

    def maint(self):
        """
        maintenance utility function to perform tasks that should happen once per cycle on the unit
        check connectivity
        check state
        update desired values
        enforce force_run and allow_run
        """
        # update state
        # pull defaults from config

        # check sync
        if self.connected:
            if self.synced:
                self.sync_timedout = False
                self.last_synced = nowts()
            elif (self.last_synced + self.time_out_delay) < nowts():
                self.sync_timedout = True
        else:
            self.stop()
            self.sync_timedout = False
            self.alarm.update([0, 0, 0])
            self.master = False
            self.standby = False
            self.holding = False
            self.cycle = False
            self.comp_state = False
            self.cond_state = False
            self.evap_state = False

        # check oos/enable_run
        if not self.enable_run:
            self.stop()

        # TODO: heatpump not connected
        # sync heatcal lstatus flags
        if self.heatcall:
            self.run_time_out_count = 0
            if self.comp_state:
                self.started = True
        else:  # unit is not in heatcall
            if self.desired_heatcall:  # but we want the unit in heatcall
                if self.started:
                    self.run_timed_out = False
                    self.run_time_out_count = 0

                # if we havent been marked as timed out and we are timed out
                elif not self.run_timed_out:
                    if self.call_time + self.run_time_out_delay < nowts():
                        self.run_timed_out = True
                        self.run_time_out_count += 1
            elif (
                not self.running
            ):  # we don't want it to run and it has stopped reset call
                self.post_heatcall_reset()
            else:
                self.log.info(f"{self.id} is stopping")

        # update alarms/status
        if self.call_duration > self.max_run_time:
            self.max_run_time_timeout = True

        self.alarm.maint(self)
        self.status.set(
            MASTER=self.master,
            STANDBY=self.standby,
            HOLDING=self.holding,
            DES_CYCLE=self.desired_cycle,
            CANT_RUN=self.cant_run,
            COMP=self.comp_state,
            COND=self.cond_state,
            EVAP=self.evap_state,
            OOS=self.out_of_service,
            DES_HC=self.desired_heatcall,
            SYNC=self.synced,
            UPDATED=self.update_sent,
            CONN=self.connected,
            STARTED=self.started,
        )

    def delete(self):
        if not self.deleted:
            self.update_sent = False
            self.deleted = True

    def set_local_alarm(self, alarm: str) -> None:
        self.alarm.set_alarm(alarm)

    def clear_local_alarm(self, alarm: str) -> None:
        self.alarm.unset_alarm(alarm)

    def __serialize__(self) -> dict:
        return {
            "sn": self.sn,
            "hello": self.hello,
            "out_of_service": bool(self.out_of_service),
            "enable_run": bool(self.enable_run),
            "states": {
                "desired": self.desired_state,
                "current_state": self.current_state,
            },
            "id": self.id,
            "name": self.name,
            "nick": self.nick,
            "topic": self.ctl_topic,
            "lwt": self.lwt,
            "lwt_sp": self.lwt_sp,
            "cant_run": self.cant_run,
            "ewt": self.ewt,
            "gpm": self.gpm,
            "mac": self.mac,
            "model": str(self.model),
            "cond_state": self.cond_state,
            "comp_state": self.comp_state,
            "force_run": self.force_run,
            "hrs": self.comp_hrs,
            "alarm": self.alarm.__serialize__(),
            "heatcall": self.heatcall,
            "running": self.running,
            "heatcall_status": [self.master, self.standby, self.holding],
            "master": self.master,
            "standby": self.standby,
            "holding": self.holding,
            "sync": self.synced,
            "connected": self.connected,
            "cycle": self.cycle,
            "desired_cycle": self.desired_cycle,
            "call_time": self.call_time,
            "last_update": self.last_update,
            "diff": self.diff,
            "deleted": self.deleted,
            "force_run_time": self.force_run_time,
            "status": self.local_status,
            "last_update_sent": self.last_update_sent,
            "update_error": self.update_error,
            "evap_state": self.evap_state
            if self.evap_state is not None
            else str(self.evap_state),
            "time_out_delay": self.time_out_delay,
            "req_time": nowts(),
            "slp": self.slp,
            "dlp": self.dlp,
            "time_since_last_update": nowts() - self.last_update,
            "healthy": self.healthy,
            "desired": self.desired_state,
            "current": self.current_state,
            "desired_heatcall": self.desired_heatcall,
            "starting": self.starting,
            "called": self.called,
            "calling": self.calling,
            "manual": self.manual,
            "ctd": self.ctd,
            "started": self.started,
            "run_timed_out": self.run_timed_out,
            "run_time_out_delay": self.run_time_out_delay,
            "run_time_out_count": self.run_time_out_count,
            "time": self.time.timestamp(),
        }

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return json.dumps(self.__serialize__())

    def __json__(self):
        Unit.JSON(self)
