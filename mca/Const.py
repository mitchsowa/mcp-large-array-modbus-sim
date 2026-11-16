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


def validate_mode(operationMode, unitMode) -> bool:
    """
    if unit is in correct mode or not is unknown assume correct
    mode should be retrieved from config.operational_mode
    """
    # mode not supported/manual
    if unitMode == UnitMode.NONE or operationMode == OperationalMode.MANUAL:
        return True
    # unit not ready/in error
    elif unitMode in (UnitMode.UNSET, UnitMode.ERROR):
        return False
    # signle pass match
    elif unitMode == UnitMode.SINGLEPASS:
        if operationMode == OperationalMode.DHWSP:
            return True
    # rtp mode match
    elif unitMode == UnitMode.RTP:
        if (
            operationMode == OperationalMode.DHWSPRTP
            or operationMode == OperationalMode.DHWSP
        ):
            return True
    # unknown unit mode
    else:
        return False
    # default return
    return False


class Mode(Enum):
    INIT = auto()
    AUTO = auto()
    MANUAL = auto()


class OperationalMode(Enum):
    DHWSP = auto()
    DHWSPRTP = auto()
    MANUAL = auto()


class UnitMode(Enum):
    UNSET = -3
    ERROR = -2
    NONE = -1
    MULIPASS = auto()  # 0
    SINGLEPASS = auto()  # 1
    RTP = auto()  # 2
