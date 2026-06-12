import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from config.Config import Config
from config.util import load_configuration


class MCAConfig(Config):
    """wraper class to allow arbitrary config but give hints for code"""

    def __init__(self, config: dict | str, logger=logging.getLogger(__name__)):
        self._parameters = {}
        self._path: list[str] = []
        self._prev = "91_previous.json"
        self._cur = "92_current.json"

        config_hash = {}
        hold = []

        if isinstance(config, list):
            hold = config[1:]
            config = config[0]

        # determine what type of config to initialize
        if isinstance(config, str):
            config_hash = MCAConfig.load_path(config)
            self._path += [config]
        elif isinstance(config, dict):
            config_hash = config

        super().__init__(config_hash, logger)

        for item in hold:
            if isinstance(item, str):
                self.update(MCAConfig.load_path(item))
            elif isinstance(item, dict):
                self.update(item)
            else:
                Exception("invalid config object type")

        # auto populate values
        self.shim()

        # check config is valid
        self.validate()

    @staticmethod
    def load_path(path: str):
        is_valid_path: bool = bool(Path(path))
        # for relative path resolve to ablsolute path
        if is_valid_path and not os.path.isabs(path):
            # set relative path relative to where execution was triggered not
            # where its running due to wrapper
            config = os.path.join(os.getcwd(), path)
        # don't do anything with valid path
        elif is_valid_path:
            pass

        return load_configuration(config)

    def update(self, update: dict[str, Any]) -> bool:
        super().update(update)
        return self.validate()

    def shim(self):
        """calculates missing values off given values if possible"""
        # fix code linting
        # normally accessing unset values would cause an exception
        if self.loop_freq is None:
            self.loop_freq = 1
        if self.stop is None:
            self.stop = True

        if (
            self.setpoint is not None
            and self.differential is None
            and self.cut_in is None
            and self.cut_out is None
        ):
            self.differential = 0
            self.cut_in = self.setpoint
            self.cut_out = self.setppoint

        if (
            self.differential is None
            and self.cut_in is not None
            and self.cut_out is not None
        ):
            self.differential = self.cut_out - self.cut_in

        if (
            self.cut_in is None
            and self.setpoint is not None
            and self.differential is not None
        ):
            self.cut_in = self.setpoint - self.differential

        if self.cut_out is None and self.setpoint is not None:
            self.cut_out = self.setpoint
        if self.setpoint is None and self.cut_out is not None:
            self.setpoint = self.cut_out
        if self.cut_out is None and self.setpoint is not None:
            self.cut_out = self.setpoint
        if (
            self.cut_out is None
            and self.setpoint is None
            and self.cut_in is not None
            and self.differential is not None
        ):
            self.setpoint = self.cut_in + self.differential
            self.cut_out = self.setpoint

        if self.lwt is None:
            self.lwt = self.setpoint

    def validate(self) -> bool:
        valid: bool = (
            self.setpoint is not None
            and self.differential is not None
            and self.cut_out is not None
            and self.cut_in is not None
        )

        if not valid:
            raise Exception(
                f"Invalid Configuration Default Setpoints Not specified {self.to_dict()} self"
            )

        return valid

    def write_config(self, dst) -> None:
        if self._path is not None:
            with open(os.path.join(self._path[-1], dst), "w") as fh:
                json.dump(self.to_dict(), fh)
        else:
            self._log.warning("no path for config determined unable to save")

    def factory_reset(self):
        """remove any user configuration and restart looks for 92_current.json and 91_previous.json"""
        if self._path is not None:
            os.remove(os.path.join(self._path[-1], self._cur))
            os.remove(os.path.join(self._path[-1], self._prev))

    def reset_config(self):
        """delete replace 92_current.json with 91_previous.json"""
        if self._path is not None:
            shutil.copy(
                os.path.join(self._path[-1], self._cur),
                os.path.join(self._path[-1], self._prev),
            )

    def backup_config(self):
        """copy 92_current.json to 91_previous.json save current state to 92_current.json"""
        if self._path is not None:
            shutil.copy(
                os.path.join(self._path[-1], self._cur),
                os.path.join(self._path[-1], self._prev),
            )

    def save_config(self):
        if self._path is not None:
            self.write_config(self._cur)
