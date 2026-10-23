import configparser
import json
import logging
import os
from typing import Any

import tomli as toml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,%(levelname)s,%(name)s,%(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


def load_resource(resource_path):
    pass


def load_configuration(config_dir, log=logger) -> dict:
    loading_config: dict = {}
    files: list = []

    # read files and sort to place in order
    log.info("loading config from {}".format(config_dir))
    for entry in os.scandir(config_dir):
        if not entry.is_file():
            log.debug("skipping {}".format(entry.name))
            continue
        file = "{}/{}".format(config_dir, entry.name)
        log.debug("scanning file {}".format(file))
        files.append(file)
    files.sort()
    log.debug("Sorted {}".format(files))

    # initialize parsers
    ini_parser = configparser.ConfigParser()

    # loop through files reading them and merging the contents
    log.debug("reading files")
    for file in files:
        tmp_config = {}
        t = file.split(".")[-1]
        log.debug("file type {} {}".format(file, t))

        # parse ini files
        if t == "ini":
            log.debug("reading ini file")
            with open(file, "r") as fh:
                log.debug("opened file {}".format(file))
                ini_parser.read_file(fh)
                if "DEFAULT" in ini_parser:
                    log.debug("loading ini DEFAULT")
                    config_merge(tmp_config, dict(ini_parser.items("DEFAULT")))
                sections = ini_parser.sections()
                sections.sort()
                for section in sections:
                    log.debug("reading section {}".format(section))
                    config_merge(tmp_config, dict(ini_parser.items(section)))
            log.debug("done reading ini file")

        # parse json files
        elif t == "json":
            contents = "readfailed"
            with open(file, "r") as fh:
                try:
                    contents = fh.read()
                    tmp_config = json.loads(contents)
                except json.decoder.JSONDecodeError as e:
                    log.error(f"{file} json decode error {contents} \n {e}")

        # parse toml files
        elif t == "toml":
            with open(file, "rb") as fh:
                try:
                    tmp_config = toml.load(fh)
                except Exception as e:
                    log.error("encountered errror {}".format(e))
        elif t == "md":
            break
        else:
            log.error("invalid config file {}".format(file))

        # end parser ifs
        # merge the most recently loaded files with the full config
        loading_config = config_merge(loading_config, tmp_config)
        # end file loop

    # add environment overrides
    env_overrides: dict = scan_environment("NWHS_MCA_")
    loading_config: dict = config_merge(loading_config, env_overrides)

    return loading_config


def config_merge(current_config: dict, overrides: dict) -> dict:
    current_config.update(overrides)
    return current_config


# Implemented by sub class
def factory_reset():
    """remove any user configuration and restart"""
    pass


def reset_config():
    """reload config from disk and apply it"""
    pass


def scan_environment(prefix="NWHS_", log=logger) -> dict[str, Any]:
    ret: dict[str, Any] = {}
    for var in os.environ:
        if var.startswith(prefix):
            ret[var.strip(prefix)] = os.environ[var]
    return ret


def nest(key: str, val: Any):
    """
    takes in a key.key2 and value and returns a dict {key:{key2:value}}
    for arbitrary depth used for dot notation updates and reads
    """
    lvls = key.split(".")
    lvls.reverse()
    ret = val
    for lvl in lvls:
        ret = {lvl: ret}
    return ret


def rget(key: str, val: Any):
    """
    access attribute of val specified by dot notation in key
    ex. {a:{b:{c:1},{d:2}}} a.b.c returns 1 a.b.d is 2 a.b returns {{c:1},{d:2}}
    key:str - dot notatino of key to access
    val: object to operate on
    """
    ary = key.split(".")
    ret = val
    for lvl in ary:
        if ret is not None:
            ret = ret.get(lvl)
    return ret
