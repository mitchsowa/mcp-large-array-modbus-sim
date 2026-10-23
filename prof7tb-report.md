# prof7tb.csv against the dev 1.8.4 register map

`prof7tb.csv` matches the dev 1.8.4 map at 10501–10860 on most points. Two problems in the profile keep a large slice of the table from updating, and the simulator is already rejecting the one poll that causes it.

The profile polls four FC03 blocks of 95 registers, stepping by 90. The map is 360 registers, 10501 through 10860. A step of 90 and a length of 95 means each block overlaps the next by 5, and the last block runs through 10865.

| Block | Address | End | Result |
|---|---|---|---|
| CMD_Dev_00 | 10501 | 10595 | Inside the map |
| CMD_Dev_01 | 10591 | 10685 | Inside the map |
| CMD_Dev_02 | 10681 | 10775 | Inside the map |
| CMD_Dev_03 | 10771 | 10865 | 5 registers past 10860 |

`validate()` rejects a read if any register in the span is outside 10501–10860, so the whole fourth read gets Illegal Address. That is the request from `192.168.1.24`: address 10771, count 95. A length of 90 on that same start address would end at 10860.

## Where the names line up

339 BACnet points, 339 moves, no duplicate object IDs. `Join_Float_Swapped` is the high-word-first packing this server uses, and each float move starts on a real float pair: `config.lwt`, `config.setpoint`, `cut_inout`, and `sensor.1` through `sensor.14`. Integer moves use `Scale` with a gain of 1. These names follow the map:

- `Cycle` is `on` (10501). `RunEnableSignal`, `System_Status`, `System_Alarm`, `Installed_Units`, and `Running_Units` follow it.
- `Tank_Set` is `config.setpoint`. `Cut_in_out_set` is `cut_inout`. `TankProbe1`–`14` are `sensor.1`–`14`.
- `ExternalHeatSignal` is `run_backup`. The six `Current*` points are the clock. `MCPLAWarningRegister` and the three relay points are 10857–10860.
- Alarm1 units 1–41, compressor hours 13–50, alarm2 units 1–24 and 46–50, all 50 alarm3 words, and alarm-local units 1–19 are on the right registers and in a poll that succeeds.

`DR_Status` (10504) is not a separate point. The map stores `state` at both 10503 and 10504, so `DR_Status` is a second copy of `System_Status`.

`Cold_Set`, `Shed_Set`, `Hot_Set`, and `Load_Set` are float joins over 10512–10519. Those registers are `static.0` on this map, so the four points publish 0.0. They sit in the reserved hole and do not shift the tank probes.

## Points wired to the wrong data array

The moves change float array at the poll boundary. The server descriptors change array 21 offsets later. The moved value lands in an array slot that has no BACnet object, and the object keeps the other array, which nothing writes. Those 53 points stay 0:

| BACnet points | Registers that were moved, then not published |
|---|---|
| Alarm1 units 42–50, compressor hours 1–12 | 10591–10611 (`alarm1.42`–`alarm1.50`, `comp.1`–`comp.12`) |
| Alarm2 units 25–45 | 10681–10701 (`alarm2.25`–`alarm2.45`) |
| Alarm-local units 25–35 | 10781–10791 (`alarml.25`–`alarml.35`) |

## Points the fourth poll never delivers

Alarm-local units 20–24 are on the right float array, but the move reads `DA_U16_02` offsets 275–279. Block 2 only fills that array through offset 274. Block 3 stores those same registers in `DA_U16_03`, and the move does not read them.

Everything from alarm-local unit 36 through `BackupRelayState` is wired correctly and is only present in block 3. Because that read is rejected, these stay at their old value:

- Alarm-local units 36–50 (10792–10806)
- `StatusUnit1`–`50` (10807–10856)
- `MCPLAWarningRegister`, `LoadRelayState`, `SourceRelayState`, `BackupRelayState` (10857–10860)
