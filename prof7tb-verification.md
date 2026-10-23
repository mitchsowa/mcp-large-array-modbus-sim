# prof7tb.csv verification against the live simulator

Checked 2026-10-23. The gateway at `192.168.1.24` is polling the simulator on `192.168.1.200:50502`, and BMS Tester Web is reading that gateway over BACnet/IP. All 339 published points match the registers the simulator is serving.

The earlier mismatch notes are in `prof7tb-report.md`. That file describes the profile before these corrections. One sentence in it is wrong: `Join_Float_Swapped` is not the high-word-first packing this server uses. `Join_Float` is. The check below is what the corrected profile does on the wire.

## What is running

| Piece | Where |
|---|---|
| Simulator | `run_sim.py --no-repl --populate --port 50502`, config 1.8.4, registers 10501–10860 |
| Gateway | `192.168.1.24`, Modbus/TCP ADU port 50502, BACnet/IP port 47808 |
| BMS Tester Web | `./bms-tester-web --profile prof7tb.csv` in `/home/msowa/Documents/GitHub/bms-tester`, API `http://127.0.0.1:8080/api/points` |

The tester target was `192.168.1.24:47808`, device 0, `poll_ms` 2000, `error` empty, `device_id_known` true.

## Profile corrections already in prof7tb.csv

Three edits were required before the table matched.

1. The four FC03 polls were length 95, stepping by 90. The last poll started at 10771 and ended at 10865, five past the map, so `validate()` rejected the whole read. Each length is now 90. The blocks are 10501–10590, 10591–10680, 10681–10770, and 10771–10860.
2. 53 moves wrote the float array the BACnet object does not read, and 10 moves read a uint array the poll does not fill. Those moves now use the array the server descriptor reads, and every register 10501–10860 is consumed once.
3. The 21 temperature and setpoint moves used `Join_Float_Swapped`. This server stores a float as the high 16 bits, then the low 16 bits (`split_float_32`). `Join_Float` keeps that order. `Join_Float_Swapped` treats the first register as the low word, so 141.0 (`17165`, `0`) becomes about `2.4e-41` and displays as 0. Integer points use `Scale` with parameters `0,1,0` and were already correct.

`Cold_Set`, `Shed_Set`, `Hot_Set`, and `Load_Set` stay 0. They join `static.0` at 10512–10519, which the map always serves as zero. `DR_Status` is the second copy of `state` at 10504, the same word as `System_Status`. `RunEnableSignal` stays 0 because `run_enable` returns 0.

## Modbus poll check

After the gateway reloaded the profile it opened a new session, `192.168.1.24:41036`. Over the next 2 seconds that session sent eight 12-byte requests and received eight 189-byte replies. A 12-byte request is one FC03 read. A 189-byte reply is 90 registers. That is the four blocks, once per second, with no exception replies.

## BACnet check

`/api/points` returned 339 points, all `status` `ok`. Each point was compared with a live read of holding registers 10501–10860, decoded with the same moves as the profile: `Scale` copies the register, `Join_Float` joins the high word and the low word.

| Result | Count |
|---|---|
| Exact match | 324 |
| Off by 1, one poll behind the simulator | 15 |
| Wrong value | 0 |
| Missing from the API | 0 |

The 15 are `TankProbe1`–`TankProbe14` and `CurrentSecond`. The tester publishes every 2 seconds and the simulator steps those values once a second, so the API sits about one count behind a simultaneous Modbus read. A second API sample one poll later moved with the simulator:

| Point | First sample | Next poll (+2 s) |
|---|---|---|
| Lw_Set | 141 | 141 |
| Tank_Set | 135 | 135 |
| Cut_in_out_set | 128 | 128 |
| TankProbe1 | 165 | 167 |
| TankProbe14 | 178 | 180 |
| CurrentSecond | 43 | 45 |
| Cycle | 1 | 1 |
| System_Status | 149 | 149 |
| Running_Units | 17 | 17 |

`Cold_Set`, `Shed_Set`, `Hot_Set`, and `Load_Set` were 0 on both samples. The same read matched the rest of the populated table: alarm words `1000+unit`, `2000+unit`, and `3000+unit`, local alarm equal to the unit number, compressor hours `5000+unit`, unit status `100+unit`, `ExternalHeatSignal` 1, `MCPLAWarningRegister` 9, and load/source/backup relay states 1, 0, and 1. The clock points follow UTC.

## Temperatures

| Point | Registers | API | Value if the words were swapped |
|---|---|---|---|
| Lw_Set | 10508–10509 | 141 | ~2.405e-41 |
| Tank_Set | 10510–10511 | 135 | ~2.404e-41 |
| Cut_in_out_set | 10520–10521 | 128 | ~2.404e-41 |
| TankProbe1–14 | 10522–10549 | stepping 161–183 | ~2.41e-41 |
| Cold_Set, Shed_Set, Hot_Set, Load_Set | 10512–10519 | 0 | 0 |
