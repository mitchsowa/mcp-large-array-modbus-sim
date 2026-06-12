import csv
import logging
import os
import re
from datetime import datetime
from enum import Flag
from struct import pack, unpack
from typing import Callable, List

from mca.Const import (
    BIN_STR_16_BIT,
    BIN_STR_32_BIT,
    LITTLE_ENDIAN_FLOAT,
    LITTLE_ENDIAN_INT,
)

log: logging.Logger = logging.getLogger(__name__)


def nowts() -> float:
    return datetime.now().timestamp()


# untility function for how plcs store value sin 4 byte split registers
def split_float(value):
    packed = pack(">f", value)
    return unpack(">HH", packed)


def split_word(value):
    packed = pack(">I", value)
    return unpack(">HH", packed)


# max_time = datetime.max
# TODO: fix y2k38 bug

"""
    used as reference
    https://www.h-schmidt.net/FloatConverter/IEEE754.html
"""


def int_as_float(value) -> float:
    float_bits = unpack(LITTLE_ENDIAN_FLOAT, pack(LITTLE_ENDIAN_INT, value))[0]
    return float(float_bits)


def float_as_int(value: float) -> int:
    """
    parses a given integer value to an IEEE 754 float

    >>> print_float_32(float_as_int(150))
    '01000011000101100000000000000000'

    >>> print_float_32(float_as_int(0))
    '00000000000000000000000000000000'

    >>> print_float_32(float_as_int(1))
    '00111111100000000000000000000000'

    >>> print_float_32(float_as_int(2))
    '01000000000000000000000000000000'

    >>> print_float_32(float_as_int(60))
    '01000010011100000000000000000000'

    >>> print_float_32(float_as_int(12.6))
    '010i00001010010011001100110011010'

    """
    # convert value given as little endian float into byte encoding
    # convert byte encoding into corisponding integer value for same bytes
    # don't ask h
    return unpack(LITTLE_ENDIAN_INT, pack(LITTLE_ENDIAN_FLOAT, value))[0]


def print_float_32(value):
    return BIN_STR_32_BIT.format(value)


def print_float_16(value):
    return BIN_STR_16_BIT.format(value)


def split_float_32(value: int) -> tuple[int, int]:
    """
    take in 32 bit integer value
    return 2 integer values representing upper and lower 16bits of argument

    >>> x = float_as_int(12.6)

    >>> a,b=split_float_32(x)

    >>> print_float_16(a) + print_float_16(b)
    '01000001010010011001100110011010'

    >>> print_float_16(a) + print_float_16(b) == print_float_32(x)
    True
    """
    str_val = BIN_STR_32_BIT.format(value)
    bits = list(str_val)
    upper = "".join(bits[:16])
    upper = int(upper, 2)
    lower = "".join(bits[16:])
    lower = int(lower, 2)
    return (upper, lower)


def ints_to_754(upper, lower):
    u_str = BIN_STR_16_BIT.format(upper)
    l_str = BIN_STR_16_BIT.format(lower)
    f_str = u_str + l_str
    f_int = int(f_str, 2)
    f_raw = int_as_float(f_int)
    return round(f_raw, 4)


def test():
    values = [-1, 0, 1, 2, 4, 32, 60, 150, 210, 12.6]
    for value in values:
        raw_int = float_as_int(value)
        up, lw = split_float_32(raw_int)
        fl = ints_to_754(up, lw)
        if fl == value:
            log.info(f"{value} works")
        else:
            log.info(f"{value} fails")


def write_csv(path: str, msg: str, gen_header: Callable[[], List[str]]) -> None:
    """write csv log to a file, create and add header if it doesn't exist"""
    create = False
    if not os.path.isfile(path):
        create = True

    try:
        if create:
            headers = [gen_header()]
        with open(path, "a") as csvfile:
            writer = csv.writer(csvfile)
            if create:
                writer.writerows(headers)
            writer.writerows([msg.split(",")])

    except OSError as e:
        if e.errno == 30:
            log.error("read-only file-system")
        elif e.errno == 28:
            log.error("No space left on disk")
        elif e.errno == 5:
            log.error("IO Error device may be damaged")
        elif e.errno == 25:
            log.error("ioctl err")
        elif e.errno == 13:
            log.error("Permission denied")

    except Exception as e:
        log.error("Undefined Error ", e)


def find_file(root_dir, target_filename=None, target_directory=None) -> list[str]:
    matches = set()

    try:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            if "/." in dirpath:  # skip hidden files
                continue
            if target_filename is not None:
                for filename in filenames:
                    if filename == target_filename:
                        full_path = os.path.abspath(os.path.join(dirpath, filename))
                        matches.add(full_path)

            if target_directory is not None:
                for dirname in dirnames:
                    if dirname == target_directory:
                        full_path = os.path.abspath(os.path.join(dirpath, dirname))
                        matches.add(full_path)

    except TypeError as e:
        log.info(f"ERROR in file walk {e}")

    return list(matches)


# end find_file


def find_current_rotation(directory, prefix="file-", suffix=".ext") -> str:
    pattern = re.compile(rf"{re.escape(prefix)}(\d+){re.escape(suffix)}$")
    max_num = -1
    max_file = None

    for filename in os.listdir(directory):
        match = pattern.match(filename)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num
                max_file = filename
    if max_file is None:
        max_file = prefix + str(1) + suffix

    return max_file


def get_next_filename(path, prefix="file-", suffix=".ext"):
    directory, _ = os.path.split(path)  # Extract the directory from the path
    pattern = re.compile(rf"{re.escape(prefix)}(\d+){re.escape(suffix)}$")

    max_num = -1
    # List files in the directory and find the highest number
    for filename in os.listdir(directory):
        match = pattern.match(filename)
        if match:
            num = int(match.group(1))
            max_num = max(max_num, num)

    next_num: int = max_num + 1
    return os.path.join(directory, f"{prefix}{next_num}{suffix}")


class IDict(dict):
    """indexed dictionary, keeps elements sorted,"""

    def __init__(self, *args, **kw):

        self.index = []
        super(IDict, self).__init__(*args, **kw)
        self.update_index()

    def update_index(self):
        self.index = list(self.keys())
        self.index.sort()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.update_index()

    def __getitem__(self, key):
        # there is a bug here if a unit id is a low integer it will cause a conflict between
        # the ditct based index and the array based index but that should only happen in testing
        # in production unit id will be a mac address and easaly disingusiable from a number
        if isinstance(key, int) or (
            isinstance(key, str) and key.isdigit() and len(key) < 4
        ):
            if int(key) < len(self.index):
                key = self.index[int(key)]

        return super().__getitem__(key)


def num_set_flags(flag: Flag):
    return flag.value.bit_count()


if __name__ == "__main__":
    import doctest

    doctest.testmod()
    test()
