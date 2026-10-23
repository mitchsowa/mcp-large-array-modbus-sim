from mca.Util import first
import logging
from logging import Logger

import mca.components
from mca.Const import MAX_TIME_TS
from mca.MCAConfig import MCAConfig
from mca.Util import nowts


class Relay:
    def __init__(
        self,
        id: str,
        name: str,
        start: str,
        end: str,
        config: MCAConfig,
        timeout=60,
        retry=3,
        logger: Logger | None = None,
    ):
        """
        represent a relay on the opto
          0     1       2     3        4      5       6
        "data/sensors/left/OptoMMP/Module/Channels/source"
        name-  the name of the relay on the plc
        start - amount of time relay needs to be on before being ready
        end - amount of time relay stays on after being shut off
        config - the global config object used to represent the relay
        logger - logging.logger compliant logger

        """
        # logger
        if logger is None:
            logger = logging.getLogger(__name__ + "." + str(id))

        self.log = logger
        self.write: str | None = None

        self.id = id
        # configuration
        self.config = config

        # id the relay is identified by generally name-location
        self.name = name

        self._timeout: int = timeout
        self._retry: int = retry

        self.req_time: float = 0

        self.value: bool = False
        """the current reported state of the pumps assume off as it is the worse case scenario"""
        self.desired_value: bool = False
        """ the deisred state of the pumps, start on to keep them running if needed"""

        self._status = True

        self.start_timer = mca.components.Timer(start, config, str(self.id) + "-start")
        self.end_timer = mca.components.Timer(end, config, str(self.id) + "-end")

        self.hello = 0
        self.sync = False
        self.quality = 0
        self.log.info(f"Created {self}")

    @property
    def nick(self):
        """return nick names of relays from config"""
        if self.config.relay_names is None:
            return self.id
        ival = getattr(self.config.relay_names, self.id)
        if ival is not None:
            return ival
        else:
            return self.id

    @property
    def timeout(self) -> int:
        """return the timeout for the sensor either hard coded default or config value"""
        if self.config.relay_timeout:
            return int(self.config.relay_timeout)
        else:
            return self._timeout

    @property
    def retry(self) -> int:
        """return number of retries either config or hard coded deafult"""
        if self.config.relay_fail_count:
            return self.config.relay_fail_count
        else:
            return self._retry

    def status(self, status=None) -> bool:
        """returns indication of if relay is healthy or not
        true - relay healthy
        false- relay unhealthy"""
        if status is not None:
            self._status = status
        if self.check_timeout():
            return False
        if self.check_unresponsive():
            return False
        if self.quality != 0:
            return False

        return self._status

    def update_quality(self, quality: int) -> bool:
        self.hello = nowts()
        self.quality = quality
        return True

    def update(self, value: bool):
        """set state of relay based on received data to indicate most recent state of sensor"""
        self.hello = nowts()
        self.log.debug(f"updating REALAY {self.id} {value}({type(value)}")
        # for testing

        if self.value != value:
            self.value = bool(value)
            if self.value == self.desired_value:
                self.log.info("relay updaed to desired time reset req_time")
                self.sync = True
                self.req_time = round(MAX_TIME_TS)
            self.log.debug(
                f"mqtt updated for {self.id} {self.value} -> {value} {bool(value)} "
            )

        return True

    def on(self):
        """
        call to turn relay on, sets desired state to on if it is off, if acutal state
        matches, begin timer, if timer has passed return true.
        ensures off timer is not running
        will continue to return true until off() has completed
        return - indicates if relay is on and ready
        """
        self.log.debug(
            f"on() dv:{self.desired_value} v:{self.value} st:{self.start_timer} "
        )
        if self.config is None or self.config.stop is None or self.config.stop:
            self.set(False)
            return False

            # if the relay is actually on
        if self.value:
            # if the timer is done we're on and ready for units
            if self.start_timer.done():
                self.log.debug("on() done ")
                return True
            # relay is on but we need to wait before starting
            elif self.start_timer.running():
                self.log.debug("on() waiting")
                return False
            # relay just came on, start the timer
            else:
                self.log.debug("on() start wait")
                self.start_timer.trigger()
                return False
        # relay isn't on yet make sure the timers are off and try to turn it on
        else:
            self.log.debug("on() start relay")
            self.end_timer.reset()
            self.start_timer.reset()
            self.set(True)
            return False

    def off(self):
        """
        call to turn relay off, initially sets timer to start running, once
        timer is done send signal to turn relay off, once signal is received
        return true to indicate relay is off
        return - indicates if relay has completed shutdown and is fully off
        """
        self.log.info(
            f"off() dv:{self.desired_value} v:{self.value} st:{self.start_timer} "
        )
        if self.config is None or self.config.stop is None or self.config.stop:
            self.set(False)
            return True

        # if relay is on
        if self.value:
            # if timer has finished send shutdown signal
            if self.end_timer.done():
                self.set(False)
                return False
            else:
                # if timer is running continue waiting
                if self.end_timer.running():
                    return False
                # if timer isn't running start it
                else:
                    self.end_timer.trigger()
                    return False
        # if relay is off return true and reset timer
        else:
            self.start_timer.reset()
            self.end_timer.reset()
            return True

    def check_timeout(self):
        """
        check if request has timed out
        """
        if nowts() > (self.hello + self.timeout_time):
            self.log.error("relay timeout")
            return True
        return False

    @property
    def timeout_time(self):
        return self.timeout * self.retry

    def check_unresponsive(self):
        """
        check if relay responds to request, if relay has been the wrong value
        for a period of time
        returns true if relay isn't updating
        """
        if self.value != self.desired_value:
            return nowts() > (self.req_time + self.config.relay_call_timeout)
        return False

    def set(self, value):
        """set the state of the sensor for logic purposes"""
        value = bool(value)
        if value != bool(self.desired_value):
            self.req_time = nowts()
            self.desired_value = value
            self.sync = False

            # the relay just turned on start the timer

    def get(self):
        """returns the current state of teh sensor"""
        return self.value

    def desired(self):
        """return the desired state of the sensor for use to mqtt"""
        return self.desired_value

    def __str__(self) -> str:
        return (
            f"id:{self.id} stus:{self.status()} v:{self.value} dv:{self.desired_value} rt:{self.req_time} q:{self.quality}\t"
            + f"\ttpc:{self.name}\t\tts({self.start_timer})\tte({self.end_timer})"
        )

    def __repr__(self) -> str:
        return self.__str__()

    def __serialize__(self):
        return {
            "id": self.id,
            "name": self.name,
            "value": self.value,
            "desired_value": self.desired_value,
            "status": self.status().real,
            "setStatus": self._status,
            "start": self.start_timer.__serialize__(),
            "end": self.end_timer.__serialize__(),
            "timeout": self.timeout,
            "retry": self.retry,
            "hello": self.hello,
            "nick": self.nick,
            "req_time": self.req_time,
            "timedout": self.check_timeout(),
            "unresponsive": self.check_unresponsive(),
            "quality": self.quality,
            "sync": self.sync,
        }
