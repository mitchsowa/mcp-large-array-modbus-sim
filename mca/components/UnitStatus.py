from enum import IntFlag, auto


class UnitStatus(IntFlag):
    MASTER = auto()  # 1 1
    STANDBY = auto()  # 2 2
    HOLDING = auto()  # 3 4
    DES_CYCLE = auto()  # 4 8
    CANTRUN = auto()  # 5 16
    COMP = auto()  # 6 32
    COND = auto()  # 7 64
    EVAP = auto()  # 8 128
    OOS = auto()  # 9 256
    DES_HC = auto()  # 10 512
    SYNC = auto()  # 11 1024
    UPDATED = auto()  # 12 2048
    CONN = auto()  # 13 4096
    STARTED = auto()  # 14 8192
    # 15
    # 16

    def set(self, **kwargs):
        for name, status in kwargs.items():
            if name in self.__class__.__members__:
                if status:
                    self._value_ |= self.__class__[name].value
                else:
                    self._value_ &= ~self.__class__[name].value


if __name__ == "__main__":
    u = UnitStatus(0)
    u.set(MASTER=True, STANDBY=True)
    print(f"{u} int({int(u)} .value({u.value} int(.value){int(u.value)}")
