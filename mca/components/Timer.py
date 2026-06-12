import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from mca.Const import MAX_TIME

log = logging.getLogger(__name__)


class Timer:
    def __init__(
        self,
        duration_key,
        config,
        id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.config = config
        """config to use for values"""

        # TODO: use uuid as default value for id
        if id is None:
            self.id = uuid4()
        else:
            self.id = str(id)

        if logger is None:
            self.log = logging.getLogger(__name__ + "." + str(id))
        else:
            self.log = logger

        self._duration = duration_key
        """string representing location of duration in config"""

        self.time = MAX_TIME
        """epoch time sensor is considered timedone"""

        self._done = False
        """if the sensor has completed"""

        self._running = False
        """wether the sensor is curently counting down"""

        self.log.info("created")

    @property
    def duration(self):
        """pull the configurable duration timer"""
        dur = getattr(self.config, self._duration)
        return int(round(float(dur)))

    @duration.setter
    def duration(self, value):
        self.config.update({self._duration: int(round(float(value)))})

    def trigger(self, duration=None):
        """reset the timer and run it"""
        if duration is None:
            duration = self.duration
        self._done = False
        self._running = True

        self.log.info("trigger")
        self.time = datetime.now() + timedelta(seconds=duration)

    def start(self):
        """if the timer isn't running run it, if it is running leave it"""
        if not self.running():
            self.trigger()

    def done(self):
        """check if the sensor is complete if its runnign and mark it as such and return if the sensor is done"""
        if self._running and datetime.now() > self.time:
            self._done = True
            self._running = False
        return self._done

    def change(self, duration):
        self.duration = duration

    def get_remaining(self) -> float:
        """return the number of seconds remaining in the sensor"""
        if self.done():
            return float(0)
        return (self.time - datetime.now()).total_seconds()

    def reset(self):
        """reset the timer to not be running or done"""
        self.log.info("Reset")
        self._done = False
        self._running = False
        self.time = MAX_TIME

    def running(self):
        return self._running

    def __str__(self):
        return f"Timer: {self.id} r{self._running} d{self._done} {self.get_remaining()}"

    def __repr__(self) -> str:
        return self.__str__()

    def __serialize__(self):
        return {
            "running": self.running(),
            "done": self.done(),
            "left": self.get_remaining(),
            "id": self.id,
            "dur": self.duration,
        }
