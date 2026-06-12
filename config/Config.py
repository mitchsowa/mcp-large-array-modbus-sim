import logging
from typing import Any

from config.util import nest, rget

log = logging.getLogger(__name__)


# Error check for if nested value deleted does it remain in known
# ex {a:{b:{c:1,d:2}, e:3},f:4}
# if b is deleted c and d are forgotten and marked as never existing
#


class Config:
    """
    Generic config wrapper clas to create arbitrary config classes for syntatic sugar
    will populate object attributes based on hash and return None for any unset elements
    as well as trigger a log when an unset object is given,

    """

    strict = False

    def __init__(
        self, config_dict: dict, logger=logging.getLogger(__name__), strict=False
    ):
        """
        take in a dictionary config and add syntatic sugar to make it easier to work with

        config_dict: dict[str,[str,int,dict,array]- the hash to use as the config
        logger - logger to use
        strict - how to handle invalid configs, if set to True app will throw exception if invalid item is accessed

        returns a config object that allows any nested key-value pair to be read and updated
            can be accessed/modified as k.subkey = value or o[key] or o.key

        """
        # use _ to denote internal values that shouldn't be exposed to apps using config

        self._log: logging.Logger = logger
        """logger """

        self._strict: bool = strict
        """whether to ignore inalid keys or throw exception"""

        # this is used again to prevent issues during initialization caused by partially initialized config
        # it inidcates a value may exist but hasn't been loaded yet and the object isn't ready for use
        self._init: bool = False
        """whether the config object has been initialize"""

        # this a workaround for an issue with the dunder override
        # some values are called before they are initalized during initalization
        # in those cases return None rather than an exception or null
        self._known: set[str] = {"_log", "_strict", "_init"}
        """list of keys that are known can be null return none for these values if they don't exist
            also used so if a key is deleted its still tracked as being none rather than non existant
        """

        # this is where we actually start building our config
        Config.update(self, config_dict)

        # config is now initialized and ready to use
        self._init = True

    def rupdate(self, key: str, value: Any):
        """
        recursive update
        key: str - takes dot notated key string of key to update
        value: Any: the value to assign


        """
        return self.update(nest(key, value))

    def update(self, update: dict[str, Any]) -> bool:
        """takes in a dict, matching values will override, merge shoudl be recusive values of the update override existing values"""
        for key, value in update.items():
            # TODO: refactor valididate key to separate function for repeat use

            if str(key).startswith("_") and str(key) != "__main__":
                if self._strict:
                    # TODO: make more specific exception
                    raise Exception(f"invalid key {key}, config can't start with _")
                else:
                    self._log.debug(f"invalid key {key} keys can't start with _")

            # add new value to config
            # if value doesn't exist create add it
            if self.get(key) is None:
                if isinstance(value, dict):
                    value = Config(value, self._log)

                self._known.update(key)
                setattr(self, key, value)

            # if value is an existing config object
            elif isinstance(self.get(key), Config):
                self.get(key).update(value)
            # if value is a raw value
            else:
                if isinstance(value, dict):
                    value = Config(value, self._log)

                setattr(self, key, value)
        # end for
        return True

    def get(self, key):
        if type(key) is int:
            key = str(key)
        try:
            return getattr(self, key)
        except RecursionError as e:
            self._log.error(f"error getting {key} {e}")
            return None

    def rget(self, key):
        return rget(key, self)

    def __str__(self):
        return str(self.to_dict())

    def to_dict(self) -> dict:
        ret = {}
        for k, v in vars(self).items():
            if k.startswith("_"):
                continue
            elif type(v) is Config:
                ret[k] = v.to_dict()
            else:
                ret[k] = v
        return ret

    def __repr__(self):
        return str(self.to_dict())

    def __html__(self):
        """display config as html used for troubleshooting"""
        html = "<table><tr><th>key</th><th>value</th></tr>"
        for k, v in vars(self).items():
            html += f"<tr><td>{k}</td><td>{v}</td></tr>"

        return f"{html}</table>"

    def __getitem__(self, key):
        return self.__getattr__(key)

    def __setitem__(self, key, value):
        self.update({key: value})

    def __getattr__(
        self,
        _name: str,
    ) -> Any:
        self._log.info(f"get({_name})")
        if _name in ["_ipython_canary_method_should_not_exist_"]:
            raise AttributeError(str(_name) + " Doesn't exist")

        if _name not in self._known:
            if self._init:
                log.debug(
                    f"{_name} not found in active config verify config contains a value and is loaded"
                )
                if Config.strict:
                    raise Exception(f"unknown config element requested {_name}")

            return None
        else:
            return getattr(self, _name)
            # TODO: added after discovery but can't be implemented for 1.007 add in next version
            # try:
            #    return getattr(self, _name)
            # except RecursionError as e:
            #    log.error(f"error retreiving {_name}: {e}")
            #    log.debug(self)
            #    return None

    # Notes for future implementation
    # def _repr_mimebundle_(self):
    # called form ipython
    # pass
