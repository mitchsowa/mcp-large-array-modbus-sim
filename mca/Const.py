from datetime import datetime, timezone
from enum import Enum, auto

MAX_SENSORS = 14
MAX_UNITS = 50
MAX_RELAYS = 2
# tick rate
MS = 1000

# used for sectioning log output
BIG_BREAK = (
    "################################################################################"
)

# used for sectioning log output
SM_BREAK = (
    "--------------------------------------------------------------------------------"
)

# debugging values for interactive and debug mode
INTER = False
# wether running in debug mode programattically
# set to true if logging is in debug mode
# prevents rendering of expensive strings during log output
DEBUG = False

FLOAT = type(1.0)  # noqa: UP003
INT = type(1)  # noqa: UP003
STR = type("")  # noqa: UP003
DIC = type({})
BOL = type(True)  # noqa: UP003
BYTES = type(bytes(0))
ARRAY: type[list] = type([])
NONE = type(None)


TZ = timezone.utc
# in for ma tim bug on fr201
BIT_MAX_32 = 2147483647
MAX_TIME = datetime.fromtimestamp(BIT_MAX_32, tz=TZ)
MAX_TIME_TS = MAX_TIME.timestamp()

LITTLE_ENDIAN_INT = "<I"
BIG_ENDIAN_INT = ">I"

LITTLE_ENDIAN_FLOAT = "<f"
BIG_ENDIAN_FLOAT = ">f"

BIN_STR_32_BIT = "{:032b}"
BIN_STR_16_BIT = "{:016b}"


class Mode(Enum):
    INIT = auto()
    AUTO = auto()
    MANUAL = auto()
