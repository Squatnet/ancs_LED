# Transport Protocol Comparison: Pi PWA ↔ Arduino ETHhost

## Use-Case Context

The Raspberry Pi hosts a PWA (Progressive Web App) that must send and receive JSON
command packets to/from the **ETHhost** — an Arduino Mega 2560 + W5100/W5500 Ethernet
shield sitting at a static IP (`192.168.0.150`) on the same local LAN.

Key constraints that shape the choice:

| Constraint | Detail |
|---|---|
| **Network topology** | Single local LAN (no internet traversal required) |
| **Arduino MCU** | ATmega2560 — limited RAM (~8 KB) and no OS |
| **Ethernet chip** | W5100 / W5500 — supports up to 4 or 8 simultaneous TCP sockets |
| **Payload shape** | JSON objects (BPM, mode, palette, FX index, zone, …) |
| **Direction (V1)** | Pi → Arduino only |
| **Direction (V2 goal)** | Bidirectional: status / health packets must flow Arduino → Pi → PWA |
| **Latency sensitivity** | Moderate — BPM-sync commands benefit from low, consistent latency |
| **Reliability** | Packet loss tolerable for FX updates; BPM-clock commands are more sensitive |
| **Implementation effort** | Arduino side must remain lean; Pi side can use full Node/Python ecosystem |

---

## Options Evaluated

1. [WebSocket](#1-websocket)
2. [UDP (raw datagrams)](#2-udp-raw-datagrams)
3. [HTTP (plain REST/polling)](#3-http-plain-restpolling)
4. [MQTT (pub/sub over TCP)](#4-mqtt-pubsub-over-tcp)

---

## 1. WebSocket

WebSocket is a full-duplex, persistent TCP connection upgraded from HTTP. Once the
handshake is done, either side can push frames at any time with minimal overhead (~2–10
byte framing vs. hundreds of bytes for a fresh HTTP request).

### Pros

- **True bidirectionality** — the server (Arduino or Pi) can push data to the other
  end without polling; ideal for the V2 status-packet requirement.
- **Low per-message overhead** — after the initial HTTP upgrade handshake (~1–2 KB),
  each frame adds only a few bytes; important given the Arduino's limited RAM.
- **Low latency** — no connection-setup round-trip per command; the persistent
  connection means a BPM-clock tick can be dispatched immediately.
- **Browser-native** — the PWA can use the built-in `WebSocket` API with no extra
  libraries; no CORS issues on a LAN.
- **Library support** — `WebSockets` by Markus Sattler is well-tested on Ethernet
  shields and has a small footprint; also available in the Arduino Library Manager.
- **Single open socket** — only one of the W5100's four sockets is consumed, leaving
  the rest free for other services.
- **Graceful reconnection** — the PWA can detect a dropped connection and reconnect
  automatically; the Arduino can flag the loss too.

### Cons

- **Connection-state management** — both sides must handle `OPEN`, `CLOSED`, and
  reconnection logic; adds a small amount of firmware complexity.
- **TCP head-of-line blocking** — if a large JSON payload is in flight, a subsequent
  time-critical command is queued behind it (same as plain HTTP).
- **W5100 socket limit** — the older W5100 chip has only 4 sockets; running a
  WebSocket server alongside the existing Ethernet stack requires careful socket
  budgeting (W5500 relaxes this to 8 sockets).
- **Initial handshake** — the HTTP upgrade adds ~1–2 KB of RAM pressure during
  connection setup; the Arduino must buffer the request headers.

### Verdict for this project

**Strong candidate.** Bidirectionality, low overhead, and the browser-native API make
it the best fit once V2 status packets are needed. The main cost is firmware complexity
for connection-state handling.

---

## 2. UDP (Raw Datagrams)

UDP sends individual datagrams with no connection setup, no acknowledgement, and no
ordering guarantees. The Ethernet shield exposes a `UDP` socket via the standard
`Ethernet.h` / `EthernetUDP` API.

### Pros

- **Lowest latency** — no connection setup, no ACK round-trip; the packet is on the
  wire immediately.
- **Smallest firmware footprint** — `EthernetUDP` is simpler than any TCP-based
  option; very low RAM and flash cost.
- **Naturally bidirectional** — the Arduino can reply to the Pi's source address
  without any separate "server" socket setup.
- **No socket-state machine** — no connection drops to handle; the Arduino just reads
  incoming datagrams in the main loop.
- **Works well for broadcast / multicast** — if the system ever needs to send the same
  command to multiple listeners on the LAN, UDP broadcast/multicast is trivial.
- **Tolerant of intermittent network** — no TCP teardown/reconnect cycle; the next
  packet simply arrives when it arrives.

### Cons

- **No delivery guarantee** — packets can be silently dropped, duplicated, or arrive
  out of order, especially under LAN congestion. BPM-clock commands that miss could
  cause visible glitches.
- **No built-in framing** — if a JSON payload exceeds one UDP datagram (MTU ~1500
  bytes on Ethernet, ~590 bytes effective on W5100), it must be fragmented manually.
- **No flow control** — a fast sender can overflow the Arduino's small receive buffer;
  the application must implement rate-limiting or acknowledgement itself.
- **Browser limitation** — the PWA **cannot** open raw UDP sockets from a browser
  context (no `UDPSocket` API in stable browsers). All UDP traffic must be proxied
  through a server process (e.g., a Node.js bridge) on the Pi — adding a layer of
  complexity.
- **Security** — UDP has no built-in authentication; on a LAN this is usually
  acceptable but worth noting for future extensions.

### Verdict for this project

**Viable for Pi → Arduino direction** if a server-side proxy exists on the Pi anyway
(Node/Python process). The browser limitation is a significant hurdle: the PWA cannot
talk UDP directly and needs a relay. If the Pi already has such a process, UDP is the
lowest-latency option, but reliability of BPM-clock commands is a concern.

---

## 3. HTTP (Plain REST / Polling)

The Arduino runs an HTTP server (using the bundled `EthernetServer`); the Pi or PWA
POSTs JSON commands and polls a status endpoint via standard HTTP requests.

### Pros

- **Simplest to implement** — `EthernetServer` / `EthernetClient` are in the Arduino
  standard library; no extra dependencies.
- **Request/response semantics** — the response to a POST can carry an ACK or current
  state, giving implicit reliability confirmation.
- **Browser-native** — the PWA uses `fetch()` with no extra libraries; no proxy needed
  for the Pi→Arduino direction.
- **Stateless** — no connection to manage; each request is independent, which
  simplifies firmware logic.
- **Firewall / proxy friendly** — although irrelevant on this LAN, it is the most
  universally supported transport.

### Cons

- **High per-request overhead** — HTTP headers (200–800 bytes per request) consume a
  significant share of the Arduino's limited RAM and Ethernet buffer.
- **High latency for frequent commands** — each BPM-tick or FX update requires a full
  TCP handshake + request + response cycle; at 120 BPM (~2 Hz) this is manageable, but
  higher-frequency updates will struggle.
- **Polling for status is inefficient** — to achieve bidirectionality, the PWA must
  poll the Arduino repeatedly; this wastes bandwidth, adds latency, and uses extra
  sockets on the W5100.
- **No true server push** — HTTP/1.1 has no push mechanism; long-polling (hanging GET)
  is a workaround but is awkward on a resource-constrained MCU.
- **Socket exhaustion** — every open `EthernetClient` consumes a W5100 socket;
  concurrent requests from the PWA and status polling can quickly exhaust the 4-socket
  limit.
- **W5100 buffer limits** — the W5100 has only 8 KB of RX/TX buffer shared across all
  sockets; large HTTP payloads can stall.

### Verdict for this project

**Acceptable for a V1-only (Pi → Arduino) prototype** where command frequency is low
and status feedback is not needed. It becomes increasingly problematic in V2 where
bidirectionality and timing precision are required. It is the easiest starting point
but likely a dead-end for the full V2 feature set.

---

## 4. MQTT (Pub/Sub over TCP)

MQTT is a lightweight publish-subscribe protocol designed for constrained devices,
typically running over TCP port 1883. A central **broker** (e.g., Mosquitto on the Pi)
routes messages between publishers and subscribers using topics.

### Pros

- **Designed for constrained devices** — the protocol was created for IoT; the packet
  format is compact (2-byte fixed header + topic + payload).
- **Bidirectional by design** — both Pi and Arduino subscribe to topics; publishing to
  a topic delivers to all subscribers simultaneously; no point-to-point socket wiring
  needed.
- **Quality of Service levels** — QoS 0 (fire-and-forget), QoS 1 (at-least-once), and
  QoS 2 (exactly-once) let you tune reliability per message type (e.g., QoS 0 for FX
  updates, QoS 1 for BPM-clock sync).
- **Retained messages** — a broker can retain the last message on a topic so a newly
  connected client (e.g., a refreshed PWA) immediately receives the current state.
- **Fan-out** — if additional subscribers are added (logging service, second PWA
  client, mobile app) they simply subscribe to the same topic; no changes to the
  Arduino firmware.
- **Decoupled architecture** — the Pi and Arduino do not need to know each other's
  addresses; they only need to reach the broker.
- **Arduino library** — `PubSubClient` by Nick O'Leary is compact and well-supported
  on Ethernet shields.

### Cons

- **Requires a broker** — Mosquitto (or similar) must run on the Pi; adds an OS-level
  service dependency and a single point of failure.
- **Extra hop latency** — every message travels Pi → broker → Arduino (or vice versa)
  rather than directly; on the same LAN this overhead is typically <1 ms but it is
  non-zero.
- **TCP connection management** — `PubSubClient` maintains a persistent TCP connection;
  the Arduino must handle reconnection logic when the broker restarts.
- **Browser-native MQTT requires WebSocket transport** — browsers cannot open raw TCP
  port 1883; the PWA must use MQTT-over-WebSocket (e.g., MQTT.js library), requiring
  Mosquitto to be configured with a WebSocket listener on a second port.
- **More moving parts** — broker config, topic naming, QoS strategy, and TLS (if
  ever needed) increase the overall system complexity vs. a direct WebSocket connection.
- **`PubSubClient` payload limit** — the default max message size is 128 bytes; this
  must be increased (`MQTT_MAX_PACKET_SIZE`) if JSON payloads exceed that.

### Verdict for this project

**Powerful long-term choice** if the system is likely to grow (more clients, logging,
external control surfaces). The retained-message and QoS features are genuinely useful
for state synchronisation. The main costs are the broker dependency and the extra
browser library. If the Pi already runs a Node/Python server process, adding Mosquitto
is low-friction.

---

## Side-by-Side Summary

| Criterion | WebSocket | UDP | HTTP (REST) | MQTT |
|---|:---:|:---:|:---:|:---:|
| Bidirectional (V2 ready) | ✅ | ✅ (w/ proxy) | ⚠️ (polling) | ✅ |
| Browser-native (no proxy) | ✅ | ❌ | ✅ | ⚠️ (needs MQTT.js) |
| Latency | Low | Lowest | High | Low |
| Per-message overhead | Low | Lowest | High | Low |
| Delivery guarantee | TCP | None | TCP | QoS 1/2 |
| Arduino library maturity | Good | Built-in | Built-in | Good |
| W5100 socket usage | 1 | 1 | 1 per client | 1 |
| Extra infrastructure | None | None | None | Broker (Mosquitto) |
| Reconnection complexity | Medium | None | None | Medium |
| Fan-out to multiple clients | Manual | Broadcast | Manual | Native |
| V1 implementation effort | Medium | Medium | **Low** | Medium |
| V2 scalability | Good | Fair | Poor | **Best** |

---

## Recommendation

### Short term (V1 — one-way Pi → Arduino)

**HTTP** is the path of least resistance for getting commands flowing. It uses only
built-in Arduino libraries and the browser's `fetch()` API, with no extra
infrastructure. Accept the latency and overhead trade-off while the command protocol
and PWA are still being iterated on.

### Medium term (V2 — bidirectional, timing-sensitive)

**WebSocket** is the recommended upgrade. It adds bidirectionality with minimal
per-message overhead, requires no broker, uses only one W5100 socket, and is supported
natively in the browser. The `WebSockets` Arduino library is mature and fits within the
Mega 2560's RAM budget. The main V2 requirement — streaming status packets back to the
PWA — is trivially satisfied by pushing frames from the Arduino's WebSocket server to
the connected Pi client.

### If the ecosystem grows (multiple control surfaces, logging, external integrations)

**MQTT** becomes attractive once the system has more than one consumer of the data
stream. Adding Mosquitto to the Pi is low-cost if a server process is already running
there, and the retained-message and QoS features simplify state synchronisation across
clients. The browser requires the additional `MQTT.js` library and a WebSocket
listener, but this is manageable.

**UDP** is best reserved for scenarios where absolute minimum latency is critical and a
server-side relay already exists on the Pi. Its lack of a browser API and the absence
of delivery guarantees make it a secondary option for this use case.

---

## References

- [WebSockets Arduino library](https://github.com/Links2004/arduinoWebSockets)
- [PubSubClient (MQTT)](https://github.com/knolleary/pubsubclient)
- [Mosquitto MQTT broker](https://mosquitto.org/)
- [MQTT.js (browser)](https://github.com/mqttjs/MQTT.js)
- [W5100 datasheet — socket limits & buffer sizes](https://docs.wiznet.io/Product/iEthernet/W5100)
- [W5500 datasheet](https://docs.wiznet.io/Product/iEthernet/W5500/w5500_ds)
- [MDN — WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)
- [MQTT specification v3.1.1](https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/mqtt-v3.1.1.html)
