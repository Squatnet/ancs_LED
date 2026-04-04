# ANCS — Networked LED Control System

**V2 — In Development**

Custom-built distributed AV installation framework for multi-zone LED matrix and strip control. A Raspberry Pi serves a PWA debug/control interface and sends JSON commands to an Ethernet-connected master Arduino, which routes them across a hybrid I2C → PJON → I2C physical bus to any number of LED client nodes spread across a space. Client separation can be hundreds of metres.

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Modules](#modules)
3. [Captive Portal / PWA Access](#captive-portal--pwa-access)
4. [V2 JSON Command Protocol](#v2-json-command-protocol)
5. [Timing Sync](#timing-sync)
6. [V1 → V2 Changes](#v1--v2-changes)
7. [Roadmap / Status](#roadmap--status)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Raspberry Pi                                                   │
│  • Serves PWA (debug / control UI)                              │
│  • Sends JSON commands to ETHhost                               │
│  • Transport: TBD (WebSocket / HTTP / UDP)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │  JSON over network (Websocket/UDP/MQTT TBD)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  ETHhost  —  Arduino Mega 2560 + Ethernet shield                │
│  • Ingests JSON commands from Pi and other network sources      │
|  • Handles physical input / client response from PJON network   |
│  • Manages global state: BPM/clock, mode, palette, FX           │
│  • Auto-randomisation logic (palettes, FX, zones)               │
│  • Forwards parsed commands downstream via I2C                  │
│  Static IP: 192.168.0.150                                       │
└────────────────────────────┬────────────────────────────────────┘
                             │  I2C  (address 2)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  IIC_2_PJON_Host  —  Arduino (any 5V)                           │
│  • I2C slave  (receives from ETHhost)                           │
│  • PJON master (broadcasts onto long-haul PJON bus)             │
│  PJON: SoftwareBitBang, pin 12                                  │
│  Bus ID: {0,0,1,53}   Device ID: 100                            │
└────────────────────────────┬────────────────────────────────────┘
                             │  PJON SoftwareBitBang (1-wire)
                             │  Broadcast — can span 100s of metres
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  PJON_2_IIC  —  Arduino (any 5V)  ×N, one per zone branch      │
│  • PJON slave  (receives broadcasts)                            │
│  • I2C master  (fans out to downstream client nodes)            │
│  PJON: SoftwareBitBang, pin 12   Device ID: Set per branch      │
│  I2C: writes to all client addresses on its local bus           │
└──────┬─────────────────────────────────────────────────┬────────┘
       │  I2C (short-range, per-branch)                  │
       ▼                                                 ▼
┌──────────────────┐                         ┌──────────────────────┐
│  LED Client(s)   │   …  ×N per branch  …   │  Control Client(s)   │
│  Arduino Mega or │                         │  Physical buttons    │
│  Uno/Nano        │                         │  switches            │
│  FastLED         │                         │  Etc                 │
│  WS2812B         │                         │                      │
└──────────────────┘                         └──────────────────────┘
```

> **Note on bidirectionality (V2 goal):** In V1 the bus was strictly
> one-way (master → clients). In V2, PJON routing will be made
> omnidirectional so clients can push status packets (current FX,
> timing drift, health) back up to the master and on to the Pi PWA.
> Client firmware does **not** run PJON directly — the PJON_2_IIC
> bridge handles all PJON overhead; clients speak only I2C, keeping
> flash/RAM usage minimal.

### Separate subsystem — Teensy video panels

`LED32T_32x64TV` and `Vid_2_Serial` are Teensy 3.x + OctoWS2811
panels driven by a direct binary serial stream from a PC
(the `movie2serial` tool). They are **not** part of the PJON/I2C
network and are managed independently.
There are no plans to re-implement these in V2
---

## Modules

### `ETHhost` — Master / Command Ingress

| Item | Value |
|---|---|
| Board | Arduino Mega 2560 + W5100/W5500 Ethernet shield |
| Static IP | `192.168.0.150` |
| Directory | `ETHhost2560/` |

Receives JSON commands from the Raspberry Pi over the local network,
parses them into typed commands, maintains global state (BPM clock,
mode, palette, FX indices, zone), and forwards serialised commands
to the I2C bridge. Handles auto-randomisation: on every 4th and 8th
clock tick, optionally picks a random palette (0–25), FX (0–19),
pulse FX (0–4), or zone (0–15).

---

### `IIC_2_PJON_Host` — I2C → PJON Bridge (master side)

| Item | Value |
|---|---|
| Board | Arduino (any 5V) |
| I2C role | Slave, address `2` |
| PJON role | Master, device ID `100` |
| PJON bus | `{0, 0, 1, 53}`, SoftwareBitBang pin 12 |
| Directory | `IIC_2_PJON_Host/` |

Sits immediately downstream of ETHhost on a short I2C run. Receives
commands via I2C interrupt, then broadcasts them onto the long-haul
PJON bus. Pulse-channel commands (types 10–17) are sent as a compact
2-byte trigger; all other commands are forwarded verbatim.

---

### `PJON_2_IIC` — PJON → I2C Bridge (client side)

| Item | Value |
|---|---|
| Board | Arduino (any 5V), one per zone branch |
| PJON role | Slave, device ID `20` |
| I2C role | Master, addresses 2..N |
| Directory | `PJON_2_IIC/` |

One board per physical zone. Receives PJON broadcasts and re-transmits
them over a local I2C bus to all LED client nodes on that branch.
`I2C_NUM` sets how many downstream clients to address.

---

### LED Client Nodes

All clients share the same I2C command protocol and FastLED rendering
loop. They differ only in matrix geometry and number of LED outputs.
Clients have no PJON library — all PJON overhead is handled by the
bridge boards above.

#### `LED328_STRIP` — 4-channel strip node

| Item | Value |
|---|---|
| Board | Arduino 328p (Uno / Nano) |
| Layout | 42×4 zigzag = 168 LEDs, 4 parallel strips |
| LED pins | 2, 3, 4, 5 |
| I2C address | 5 |
| Directory | `LED328_STRIP/` |

Zone and sub-zone bitmask commands (types 8, 9) allow per-strip
addressing. Includes `plasma()` and `simpleStrobe()` FX not present
on the matrix variants. 14 auto FX, 9 pulse FX.

This is by far the most commonly used client type
#### `LED2560_14x60R2` — 60×14 horizontal matrix

| Item | Value |
|---|---|
| Board | Arduino Mega 2560 |
| Matrix | 60×14 = 840 LEDs, single pin |
| LED pin | 3 |
| I2C address | 2 |
| Directory | `LED2560_14x60R2/` |

16 auto FX. Small font (`FontMatrise`) with `SCROLL_LEFT` scrolling.
Autonomous FX cycling every 30 s when not receiving commands.

#### `LED2560_8x8T_R3` — 8×8 tile matrix

| Item | Value |
|---|---|
| Board | Arduino Mega 2560 |
| Matrix | 3×4 tiles × 8×8 = 24×32 px — 768 LEDs |
| LED pins | 5, 7, 9, 11 (4 outputs) |
| I2C address | 2 |
| Directory | `LED2560_8x8T_R3/` |

17 auto FX including `scrollText`, `heartBeat`, `rainbow`, `sinelon`,
`bouncingTrails`, `autoShapes`, and more. 10 pulse FX. 8 mirror modes
(horizontal, vertical, quadrant, triangle variants). Large font
(Font16x24) with `SCROLL_UP` scrolling.

#### `LED2560_8x32S_R2` — dual-strip matrix

| Item | Value |
|---|---|
| Board | Arduino Mega 2560 |
| Matrix | 32×16 = 512 LEDs, 2 outputs |
| LED pins | 5, 7 |
| I2C address | 2 |
| Directory | `LED2560_8x32S_R2/` |

16 auto FX, `SCROLL_UP` text direction.

### Physical Control Client Nodes

Field-deployed control surfaces wired with physical inputs — momentary buttons, toggle switches, rotary encoders, potentiometers, capacitive pads, PIR sensors, etc. Like all other client nodes, these are I2C-only (no PJON library overhead) and sit on a `PJON_2_IIC` branch alongside LED nodes.

When a control is actuated, the node packages the event as a JSON status packet and sends it upstream over I2C to the branch bridge, which forwards it onto the PJON bus, which delivers it to `IIC_2_PJON_Host`, and from there via I2C to ETHhost. ETHhost processes the input — updating global state and/or triggering commands — then re-broadcasts the resulting command downstream to the relevant LED nodes.

```
[Physical input]
      │
      ▼
Control node (I2C slave)
      │  I2C upstream → PJON_2_IIC
      │  PJON → IIC_2_PJON_Host
      │  I2C → ETHhost
      ▼
ETHhost  (processes input, updates state)
      │  I2C → IIC_2_PJON_Host
      │  PJON broadcast → PJON_2_IIC(s)
      │  I2C fanout
      ▼
LED client nodes (respond to command)
```

**Planned input types and mappings:**

| Input | Action |
|---|---|
| Momentary button | Trigger a pulse channel (0–7) |
| Rotary encoder | Increment / decrement BPM, palette, or FX index |
| Potentiometer | Set hue speed, fade time, or brightness |
| Toggle switch | Change mode (auto / pulse) or enable auto-randomisation |
| Tap pad | BPM tap-tempo — ETHhost calculates interval from successive taps |
| PIR / proximity sensor | Trigger a pulse or switch to a defined mode on presence |
| NFC Card readers | Set a value based on the card used |
Because the bus is omnidirectional, ETHhost can also send feedback back to a control node — for example, lighting an indicator LED on a panel to confirm the current mode, or driving a small display showing BPM or active FX index.

Control nodes are expected to use 328p-class boards (Uno / Nano) to keep cost and power draw low. Each branch can mix LED and control clients freely; the `PJON_2_IIC` bridge addresses them by their individual I2C addresses.

---

### Raspberry Pi — PWA Host

Serves a Progressive Web App providing:
- Real-time control of all command parameters (BPM, mode, palette,
  FX, pulse channels, hue speed, zones)
- Text input for LED matrix scroll messages
- Live status view from client nodes (V2 / omnidirectional routing)
- Per-zone control views routable via URL parameter (`?zone=N`)

Sends JSON commands to ETHhost over WebSocket, served by the same
Node.js process that handles captive portal routing (see
[Captive Portal / PWA Access](#captive-portal--pwa-access)).

--- More LED client types are expected to be defined

---

## Captive Portal / PWA Access

The Pi operates as a standalone Wi-Fi access point with no upstream
internet connection. When a phone or laptop joins the network, the OS
detects the absence of internet and automatically surfaces a "Sign in
to network" prompt — this redirects the user directly to the PWA
control interface, with no URL to type or app to install.

### How it works

```
User scans QR / joins open Wi-Fi "ANCS"
        │
        ▼
Device gets IP from dnsmasq DHCP
        │
        ▼
OS sends captive-portal probe request
(Apple: /hotspot-detect.html, Android: /generate_204,
 Windows: /ncsi.txt, Firefox: /canonical.html)
        │
        ▼  iptables redirects all port-80 traffic → Node server
Node server intercepts probe → responds with redirect or
non-2xx so OS pops "Sign in" sheet
        │
        ▼
Browser loads http://ancs.local/ → PWA served by Node
        │
        ▼
Service worker caches all assets → PWA works offline
for rest of session even if Pi reboots
```

### Pi setup

| Component | Role |
|---|---|
| `hostapd` | Broadcasts open Wi-Fi AP — SSID `ANCS`, no password |
| `dnsmasq` | DHCP server; DNS wildcard resolves every hostname to `192.168.4.1` |
| `iptables` | Redirects all TCP port 80 → Node server port 3000 |
| Node.js server | Serves PWA; handles OS-specific captive portal probe URLs |

**Key `hostapd` settings:**
```ini
ssid=ANCS
hw_mode=g
channel=6
ignore_broadcast_ssid=0
# No wpa_passphrase — open network
```

**`dnsmasq` DNS wildcard:**
```
address=/#/192.168.4.1
```

**`iptables` redirect:**
```bash
iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 3000
```

**Node captive portal probe handler:**
```typescript
// Probe URLs sent by each OS to detect captive portals
const PROBES = [
  '/hotspot-detect.html',      // Apple (iOS / macOS)
  '/library/test/success.html',// Apple (older)
  '/generate_204',             // Android / Chrome
  '/ncsi.txt',                 // Windows
  '/canonical.html',           // Firefox
  '/connecttest.txt',          // Windows 10+
];

app.use((req, res, next) => {
  if (PROBES.includes(req.path)) {
    // Redirect to PWA root — OS pops the "Sign in" sheet
    return res.redirect('http://ancs.local/');
  }
  next();
});
```

### Per-zone routing

QR codes can be printed and mounted next to each physical zone or
fixture. Each code encodes a direct URL:

| QR content | Result |
|---|---|
| `http://ancs.local/` | Full control panel |
| `http://ancs.local/?zone=2` | Zone 2 controls only |
| `http://ancs.local/?node=strip-a` | Single node control |

The PWA reads the `zone` / `node` query param on load and
pre-filters the control UI accordingly.

### Project structure

```
ancs-portal/
├── server/
│   ├── app.ts               # Express server + captive portal middleware
│   ├── routes/
│   │   ├── captive.ts       # OS probe interception + redirect
│   │   └── api.ts           # WebSocket / REST bridge to ETHhost
│   └── types/
│       └── index.ts
├── pwa/
│   ├── index.html
│   ├── manifest.json
│   ├── service-worker.ts    # Caches all assets for offline use
│   ├── styles/
│   │   └── main.css
│   └── src/
│       ├── main.ts
│       ├── components/
│       │   ├── ControlPanel.ts
│       │   ├── BpmControl.ts
│       │   ├── PaletteControl.ts
│       │   ├── FxControl.ts
│       │   ├── PulseControl.ts
│       │   └── TextControl.ts
│       └── api/
│           └── client.ts    # WebSocket client → Node server → ETHhost
├── shared/
│   └── protocol.ts          # Shared JSON command types
├── package.json
└── tsconfig.json
```

### Notes

- **No BLE.** Web Bluetooth is unsupported on iOS Safari and requires
  HTTPS, making it impractical for a local plain-HTTP setup.
- **No login.** The captive portal presents controls immediately —
  there is no authentication step.
- **Offline resilience.** The service worker caches the full PWA on
  first load. If the Pi restarts mid-session, already-loaded clients
  retain the UI and reconnect automatically when the WebSocket comes
  back up.

---

## V2 JSON Command Protocol

> **Status: draft.**

### Two-layer protocol — JSON front-end, compact wire format back-end

JSON is used **only between the Pi and ETHhost**. ETHhost (Arduino
Mega 2560) has enough flash and RAM to run ArduinoJSON and parse
incoming packets comfortably.

Everything downstream of ETHhost — I2C to the bridge, PJON on the
long run, I2C on the client branches — continues to use the **compact
integer wire format** from V1. This was a deliberate V1 design choice:
client nodes (especially 328p-class boards) cannot afford the flash
and RAM overhead of ArduinoJSON, and compact integer pairs keep
packets small and parsing trivially fast with `atoi()`.

```
Pi  ──── JSON ────▶  ETHhost  ─── compact wire ───▶  IIC_2_PJON_Host
    (named fields,            ("type,value" CSV)          │
     ArduinoJSON)              ETHhost translates     PJON broadcast
                          │
                     PJON_2_IIC (×N)
                          │
                        I²C fanout
                          │
                      LED / Control clients
                      (never see JSON)
```

Client firmware is unchanged in structure — the bridge layer is
transparent to them. The only new firmware work on the client side
is handling the new `text` and `sync` wire commands (see table below).

### JSON envelope (Pi → ETHhost)

```json
{
  "target": "all" | "zone:N" | "node:ID",
  "command": "<command name>",
  "params": { }
}
```

### Command reference

ETHhost maps each incoming JSON command to its compact wire equivalent
before forwarding.

| V2 JSON command | V2 params | Wire format (I2C/PJON) | Notes |
|---|---|---|---|
| `clock` | `{ "step": 64 }` | `"1,64"` | |
| `mode` | `{ "mode": "auto" }` | `"2,0"` | `auto`=0, `pulse`=1 |
| `palette` | `{ "index": 3 }` | `"5,3"` | |
| `fx` | `{ "index": 7 }` | `"6,7"` | |
| `pulseFx` | `{ "index": 2 }` | `"7,2"` | |
| `zone` | `{ "mask": 15 }` | `"8,15"` | |
| `pulse` | `{ "channel": 0 }` | `"10"` | Channels 0–7 → types 10–17 |
| `hueSpeed` | `{ "value": 3 }` | `"20,3"` | |
| `runTime` | `{ "multiplier": 2 }` | `"21,2"` | |
| `fadeTime` | `{ "value": 50 }` | `"23,50"` | |
| `text` | `{ "message": "Hello", "user": "@ancs" }` | `"30,<len>,<chars>"` | New — matrix nodes only |
| `sync` | `{ "bpm": 120, "step": 0, "ts": 1743724800000 }` | `"31,<bpm>,<step>"` | New — all clients |
| `status` | _(none — client-initiated)_ | `"32,<type>,<val>"` | Upstream only |

> **Text wire format note:** because the wire is ASCII CSV, the `text`
> command will be sent as a length-prefixed byte sequence. The exact
> framing (e.g. chunked with ACK, or single packet with length byte)
> is TBD pending firmware prototyping — 328p SRAM limits (~2 KB) cap
> maximum message length in a single I2C transaction.

### Text display

The `text` command replaces the V1 hardcoded scroll string. The PWA
sends free-form text (message, label, announcement); ETHhost
translates it to the compact wire form and forwards it to any matrix
node capable of scrolling. This replaces the old Twitter-to-LED
pipeline — the display capability remains, with content now driven
by the PWA instead of a social media feed. Strip nodes (`LED328_STRIP`)
ignore the `text` command.

### Bidirectional flow

Client status responses (e.g. `status`, tap-tempo events from control
nodes) travel the reverse path using the same compact wire format:

```
Client  ──wire──▶  PJON_2_IIC  ──PJON──▶  IIC_2_PJON_Host  ──I²C──▶  ETHhost
                                │
                              translate
                              to JSON
                                │
                              ──JSON──▶  Pi PWA
```

---

## Timing Sync

Client nodes may be hundreds of metres apart, making clock drift a
real problem. V2 introduces periodic automatic sync:

1. The master periodically broadcasts a `sync` command containing the
   current BPM, beat step, and a Unix millisecond timestamp.
2. Each client node receives the sync via the normal I²C path and
   adjusts its internal step counter and timing accordingly.
3. With omnidirectional routing, clients can also request a resync by
   sending a `status` packet upstream.

This replaces the V1 approach where clock was held only at the master
and clients drifted indefinitely with no correction mechanism.

---

## V1 → V2 Changes

### Removed

| Item | Reason |
|---|---|
| OSC (Open Sound Control) | Replaced by JSON — no DSP host required |
| Reaktor 6 / DAW as command source | Commands now come from Pi PWA |
| Godot control application | Replaced by Pi-served PWA |
| Twitter / social media integration | Out of scope; text display retained via `text` command |
| Hardcoded scroll strings in firmware | Dynamic text from PWA via `text` command |
| One-way-only bus routing | Replaced by omnidirectional I²C/PJON routing |

### Added / Changed

| Item | Detail |
|---|---|
| Raspberry Pi PWA host | Serves debug and control UI over the local network |
| JSON command protocol | Named commands replace magic integer type codes |
| Dynamic text rendering | Free-form text sent from PWA to any matrix node |
| Omnidirectional routing | Clients push status packets back to master |
| Automatic time sync | Periodic `sync` broadcast corrects client drift |
| Captive portal access | Open Wi-Fi soft AP; OS-native redirect delivers PWA without manual URL entry |

### Carried forward

- PJON SoftwareBitBang transport (proven reliable over long cable runs)
- FastLED rendering engine on all client nodes
- 18 custom gradient palettes (ColorBrewer-derived)
- WS2812B LED hardware throughout
- I²C bridge topology (client boards stay I²C-only, no PJON overhead)
- Compact integer wire format on I2C/PJON (client nodes never parse JSON)
- All existing auto FX and pulse FX

---

## Roadmap / Status

| Item | Status |
|---|---|
| Root README | ✅ Written |
| ETHhost V2 — JSON ingress, command parser | 🔲 Planned |
| ETHhost V2 — bidirectional routing | 🔲 Planned |
| IIC_2_PJON_Host V2 — omnidirectional | 🔲 Planned |
| PJON_2_IIC V2 — omnidirectional | 🔲 Planned |
| LED client V2 — JSON command parser | 🔲 Planned |
| LED client V2 — time sync receiver | 🔲 Planned |
| LED client V2 — dynamic text command | 🔲 Planned |
| Raspberry Pi PWA — control UI | 🔲 Planned |
| Raspberry Pi PWA — status dashboard | 🔲 Planned |
| Raspberry Pi PWA — per-zone URL routing (`?zone=N`) | 🔲 Planned |
| Pi soft AP (`hostapd` + `dnsmasq`) | 🔲 Planned |
| Captive portal server (OS probe handling) | 🔲 Planned |
| PWA service worker / offline cache | 🔲 Planned |
| Pi ↔ ETHhost transport (WebSocket) | ⚠️ TBD |
| Teensy video panels (LED32T / Vid_2_Serial) | 🔲 Separate — unchanged for now |

---

*ANCS — Custom Built Audio / Visual — [autoav.co.uk](http://www.autoav.co.uk)*  
*Last updated: April 2026*
