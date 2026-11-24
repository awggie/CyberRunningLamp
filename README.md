# CyberLamp

A cyberpunk ambient lamp built from a salvaged **Hella DRL / turn-signal LED module** pulled from a wrecked Mercedes-Benz EQB (X243) headlight. A Seeed XIAO ESP32S3 drives the module's amber and white LED strings independently. You control it from a web page on home Wi-Fi, a push button, or the serial monitor.

Modes: off · steady amber · steady white · amber breathing · failing-streetlight glitch · glitch + white arc flashes.

---

## The LED module

| Item | Value |
|---|---|
| Maker | Hella (logo stamped on heatsink) |
| Heatsink stamp | `AB 222.090-02 R7`, `DC` |
| Board markings | `8930F`, `234 358 -10`, `4823`, `5.6`, `ST` |
| Closest listed part | Hella 222090-51 AB, EQB X243 DRL + turn signal module (board code `8927F … 00234357`); ours is likely the sibling/other-side variant |
| Driver on board | None. The constant-current driver lives in the headlamp control unit. The board is bare LED strings plus a few passives (a `30C` 20 kΩ resistor, likely a brightness-bin code, and a small 3-terminal part) |

### Measured pinout

Pins are numbered **1 = leftmost**, with the board oriented connector-up and LEDs below.

| Pin | Function | Forward voltage |
|---|---|---|
| 1 | Common negative (cathode) for both strings | — |
| 2 | Amber string + (turn signal) | 22.93 V @ 2 mA · 23.86 V @ 30 mA |
| 4 | White string + (DRL) | 15.95 V @ 30 mA |
| 3, 5+ | Not LED strings; suspected bin resistor / temperature sensor | — |

Notes from bench testing on the Jesverty SPS-3010V in CC mode:
- 30 mA is plenty bright for ambient use. The amber string handled a brief 730 mA (~20 W) burst with no damage and no heat concerns.
- The amber string won't light below about 22 V. That's why it looked dead when probing stopped at 20 V.
- The "yellow" chips are phosphor-converted **white** LEDs; the orange chips are phosphor-converted **amber**.

---

## How it works

```
USB-C 5 V ──► XIAO ESP32S3 ──5V pin──► XL6019 boost ──► +28.5 V rail
                    │                                        │
                    │ D0 (PWM)                               ├─► PNP switch ─► LM317 (27 mA) ─► module pin 2 (amber)
                    │ D1 (PWM)                               └─► PNP switch ─► LM317 (27 mA) ─► module pin 4 (white)
                    │ D3 ◄── mode button                                                         module pin 1 ─► GND
```

- **Why a 28.5 V rail:** the amber string needs ~24 V, plus ~3 V of headroom for the LM317 and a little for the PNP switch.
- **Why two separate current sources:** pin 1 is a shared negative, so the strings can't be switched independently on the low side. Each one gets its own LM317 current source and its own high-side PNP switch.
- **Current per string:** 1.25 V ÷ 47 Ω ≈ **27 mA** at full PWM. That's the maximum brightness; the web sliders and effects only go dimmer.
- **Power budget:** both strings at full draw about 1.5 W of LED power, roughly **0.4–0.5 A from USB-C** including the ESP32. Any decent USB-C charger works.

### Per-channel schematic (build two: amber on D0 → pin 2, white on D1 → pin 4)

Connection list for the amber channel. The white channel is identical, with **D1** in place of D0 and **module pin 4** in place of pin 2.

| From | Through | To |
|---|---|---|
| XIAO **D0** | 4.7 kΩ | 2N3904 **base** |
| 2N3904 **base** | 100 kΩ | GND |
| 2N3904 **emitter** | — | GND |
| 2N3904 **collector** | 10 kΩ | 2N5401 **base** |
| 2N5401 **base** | 22 kΩ | +28.5 V rail |
| 2N5401 **emitter** | — | +28.5 V rail |
| 2N5401 **collector** | — | LM317 **IN** |
| LM317 **OUT** | 47 Ω | LM317 **ADJ** |
| LM317 **ADJ** | — | module **pin 2** (amber +) |
| module **pin 1** | — | GND (shared by both channels) |

TO-92 pinout for both transistors, flat face toward you, legs down: **E – B – C**. LM317 (TO-220), tab away from you, legs down: **ADJ – OUT – IN**. Double-check against the datasheet for the exact parts you pull.

- XIAO pin **HIGH → NPN on → PNP on → LEDs lit**. The logic isn't inverted.
- The **22k** keeps the PNP off when the NPN is off. The **100k** keeps the NPN off while the XIAO boots, so the lamp doesn't flash at power-up.
- Put a **10 µF / 50 V** (or larger, ≥35 V rated) electrolytic across the 28.5 V rail and GND, right at the XL6019 output.
- Every ground is shared: XIAO GND, XL6019 IN−/OUT−, both 2N3904 emitters, and module pin 1.

---

## Parts list (checked against PartsInventory)

Everything required is already in the office. IDs refer to `awggie/PartsInventory/parts-inventory.csv`.

| Qty | Part | Inventory ID | Location | Notes |
|---|---|---|---|---|
| 1 | Seeed XIAO ESP32S3 | MCU-003 (2 on hand) | Drawer 2 | Headers not soldered yet. Also needs its 2.4 GHz antenna on the U.FL connector |
| 1 | XL6019 boost module | MOD-006 (2 on hand) | Parts bin row 4 | ~5–35 V out; set to 28.5 V **before** connecting anything |
| 2 | LM317 (TO-220) | REG-001 (5) / IC-001 (2) | Drawer 2 | No heatsink needed: worst case ~0.3 W on the white channel |
| 2 | 2N5401 PNP | TR-001 | Drawer 2 | 150 V rated; 2N2907 (60 V) also works |
| 2 | 2N3904 NPN | TR-001 | Drawer 2 | 2N2222 / BC547 also fine |
| 2 each | Resistors: 47 Ω, 4.7 kΩ, 10 kΩ, 22 kΩ, 100 kΩ | RES-001 | Drawer 3 | 47 Ω sets the current. 22 Ω + 22 Ω in series (≈28 mA) also works |
| 1 | Electrolytic cap, ≥35 V (10 µF/50 V or larger) | CAP-003 | Drawer 3 | Confirm a ≥35 V value in the kit |
| 1 | Tactile push button | SW-001 | Bottom drawer | Mode cycling |
| 1 | Perfboard | PROTO-004 | Parts bin row 3 | Breadboard first on PROTO-002 |
| — | Screw terminals, headers, 24 AWG wire, heat shrink | CON-009, CON-008, WIRE-004, CONS-005 | Parts bin / wire rack | |
| — | 30 AWG wire for the module connector | WIRE-005 | Wire rack | **No mating plug on hand**: solder fine wires to the pins/pads for pins 1, 2, 4 |
| opt. | 0.96" SSD1306 OLED | KIT-001-09 | Crates | Future: status / telemetry display on D4/D5 (I²C) |

---

## Build and bring-up

1. **Set the boost first.** Power the XL6019 from the bench supply at 5 V (current limit ~0.5 A) with nothing connected to its output. Turn its trim pot until your multimeter reads **28.5 V**.
2. **Breadboard one channel.** Wire the amber channel per the schematic and feed it from the boost. Drive the 4.7k with a jumper to 3.3 V instead of the XIAO. The amber string should light at ~27 mA. Check with the bench supply's ammeter or put the DMM in series.
3. **Add the second channel**, then the XIAO and the button.
4. **Flash the firmware** (below). Once it works, move everything to perfboard.

## Firmware

Located in `firmware/CyberLamp/`.

1. Arduino IDE → Boards Manager → install **esp32 by Espressif** (version 3.x).
2. Select board **XIAO_ESP32S3**.
3. Copy `secrets.example.h` to `secrets.h` and enter your 2.4 GHz Wi-Fi name and password. `secrets.h` is git-ignored.
4. Upload, then open the Serial Monitor at 115200 baud. It prints the lamp's address once connected.

### Controls

- **Web:** open `http://cyberlamp.local` from any device on your home Wi-Fi. If `.local` doesn't resolve on your Android phone, use the IP address printed in the serial monitor, or set a DHCP reservation on your router so the address never changes.
- **Button:** each press cycles to the next mode.
- **Serial:** send `0`–`5` (off, amber, white, breathe, glitch, arcing).

If Wi-Fi is down or not configured, the lamp still runs on the button and serial.

### Security note

The control page has no login: anyone on your home network can change the lamp. That's normal for a LAN gadget, but **don't port-forward it to the internet**. For remote access, use a VPN into your home network (e.g. Tailscale) instead.
