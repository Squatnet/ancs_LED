"""
ANCS Pico W — Dual-mode web server
====================================
Boot behaviour:
  1. Try to load wifi.json for STA credentials.
  2. Connect to the network as a Wi-Fi client (STA mode).
        • If connected  → serve the Svelte app on the assigned LAN IP.
  3. If wifi.json is missing / credentials fail within STA_TIMEOUT s
        → fall back to open AP mode (SSID: "ANCS", no password).
        • Start a UDP DNS spoof server on port 53 — resolves every
          hostname to 192.168.4.1 so OS captive-portal (no internet detection) probes are
          intercepted and the "Sign in to network" sheet appears
          automatically on every platform.
        • HTTP server intercepts OS probe URLs and issues a 302
          redirect so the device pops the sign-in sheet and loads
          the Svelte app with no URL to type.
HTTP server:
  • Listens on port 80 in both AP and STA modes.
    • Serves files from the "www" directory, with correct MIME types.
    • SPA fallback: if a requested file isn't found, serves index.html.
    • Only supports GET and HEAD methods; other methods get a 405 response.
    • Catches unexpected errors and returns a 500 response with the error message.
DNS server (AP mode only):
  • Listens on UDP port 53 and responds to every query with a minimal DNS A-record reply
    pointing to 192.168.4.1, ensuring that all captive-portal detection probes are redirected to the Pico's web server.
OLED display:
    • Not implemented yet, but the plan is to show the current mode (AP/STA), IP address, and maybe some connection status or error messages.
"""

import asyncio
import json
import network
import os
import socket
import time
from machine import Pin, I2C, Timer
from ssd1306 import SSD1306_I2C
# ── Configuration ────────────────────────────────────────────────────────────

AP_SSID     = 'ANCS'
AP_IP       = '192.168.4.1'
AP_SUBNET   = '255.255.255.0'
AP_GATEWAY  = '192.168.4.1'
AP_DNS      = '192.168.4.1'

PORT        = 80
WEB_ROOT    = 'www'
STA_TIMEOUT = 15          # seconds to wait for STA connection
WIFI_CONFIG = 'wifi.json'
FW_VERSION  = '2026-04-04-ap-yield-fix-6'

# ── OS captive-portal probe paths (all platforms) ────────────────────────────

PROBE_PATHS = {
    '/hotspot-detect.html',        # Apple iOS / macOS
    '/library/test/success.html',  # Apple (older)
    '/generate_204',               # Android / Chrome
    '/gen_204',                    # Android (alternate)
    '/ncsi.txt',                   # Windows 7-10
    '/connecttest.txt',            # Windows 10+
    '/fwlink',                     # Windows captive portal
    '/canonical.html',             # Firefox
    '/success.txt',                # Generic
    '/redirect',                   # Some Android builds
}

# ── MIME types ────────────────────────────────────────────────────────────────

MIME = {
    '.html': 'text/html; charset=utf-8',
    '.css':  'text/css; charset=utf-8',
    '.js':   'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg':  'image/svg+xml',
    '.png':  'image/png',
    '.jpg':  'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif':  'image/gif',
    '.ico':  'image/x-icon',
    '.webp': 'image/webp',
    '.txt':  'text/plain; charset=utf-8',
    '.map':  'application/json; charset=utf-8',
}

# ── Global state set during boot ─────────────────────────────────────────────

mode      = 'AP'   # 'STA' | 'AP'
server_ip = AP_IP

# ─────────────────────────────────────────────────────────────────────────────
# Network setup
# ─────────────────────────────────────────────────────────────────────────────

def load_wifi_config():
    """Return (ssid, password) from wifi.json, or (None, None) if missing/invalid."""
    try:
        with open(WIFI_CONFIG) as f:
            cfg = json.load(f)
        return cfg.get('ssid'), cfg.get('password')
    except Exception:
        return None, None


def try_sta(ssid, password):
    """Attempt STA connection; return assigned IP string on success, else None."""
    global mode, server_ip
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print('[STA] Already connected, IP:', ip)
        mode, server_ip = 'STA', ip
        return ip

    print('[STA] Connecting to', ssid, '...')
    wlan.connect(ssid, password)
    deadline = time.time() + STA_TIMEOUT
    while time.time() < deadline:
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print('[STA] Connected, IP:', ip)
            mode, server_ip = 'STA', ip
            return ip
        time.sleep(0.5)

    wlan.active(False)
    print('[STA] Failed — falling back to AP mode')
    return None


def start_ap():
    """Start open access point with fixed IP 192.168.4.1."""
    global mode, server_ip

    sta = network.WLAN(network.STA_IF)
    sta.active(False)

    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(ssid=AP_SSID, security=0)    # security=0 → open, no password
    ap.ifconfig((AP_IP, AP_SUBNET, AP_GATEWAY, AP_DNS))

    deadline = time.time() + 10
    while not ap.active() and time.time() < deadline:
        time.sleep(0.2)

    mode, server_ip = 'AP', AP_IP
    print('[AP] Broadcasting SSID:', AP_SSID, '  IP:', AP_IP)


def boot_network():
    """Load the wifi config and try to connect as a client; if it fails, start an open AP."""
    ssid, password = load_wifi_config()
    if ssid:
        ip = try_sta(ssid, password)
        if ip:
            return
    start_ap()


# ─────────────────────────────────────────────────────────────────────────────
# DNS spoof server (AP mode only)
# ─────────────────────────────────────────────────────────────────────────────

def _dns_reply(query: bytes, ip: str) -> bytes:
    """
    Build a minimal DNS A-record reply pointing every hostname to *ip*.
    Handles single-question A queries, which is all OS captive probes send.
    """
    packed_ip = bytes(int(x) for x in ip.split('.'))

    # Extract only the first DNS question (QNAME + QTYPE + QCLASS).
    # Some clients include additional sections; echoing query[12:] can make
    # malformed replies if counts don't match.
    q_end = 12
    q_len = len(query)
    while q_end < q_len:
        label_len = query[q_end]
        q_end += 1
        if label_len == 0:
            break
        q_end += label_len
    if q_end + 4 > q_len:
        raise OSError('bad dns question')
    question = query[12:q_end + 4]

    # Header: copy TX id, set QR+AA (+RD if requested), 1 question, 1 answer
    req_flags = (query[2] << 8) | query[3]
    rd_flag = req_flags & 0x0100
    resp_flags = 0x8400 | rd_flag
    header = (
        query[:2]          # transaction ID
        + bytes((resp_flags >> 8, resp_flags & 0xFF))
        + b'\x00\x01'     # QDCOUNT 1
        + b'\x00\x01'     # ANCOUNT 1
        + b'\x00\x00'     # NSCOUNT 0
        + b'\x00\x00'     # ARCOUNT 0
    )

    answer = (
        b'\xc0\x0c'       # name: pointer to offset 12 (question name)
        + b'\x00\x01'     # type A
        + b'\x00\x01'     # class IN
        + b'\x00\x00\x00\x3c'  # TTL 60 s
        + b'\x00\x04'     # RDLENGTH 4
        + packed_ip
    )
    print('[DNS] Replying with IP', ip)
    return header + question + answer


async def dns_server():
    """Async UDP DNS spoof — resolves every query to AP_IP."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', 53))
    sock.setblocking(False)
    print('[DNS] Spoof server listening on UDP:53')

    while True:
        handled = False
        try:
            data, addr = sock.recvfrom(512)
            if len(data) >= 12:
                handled = True
                print('[DNS] Received query from', addr)
                try:
                    sock.sendto(_dns_reply(data, AP_IP), addr)
                except Exception as exc:
                    print('[DNS] Failed to build/send reply:', exc)
        except OSError:
            pass
        if handled:
            await asyncio.sleep_ms(1)
        else:
            await asyncio.sleep_ms(20)


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

def safe_path(req_path: str) -> str:
    """Sanitise URL path and return the corresponding filesystem (webroot) path."""
    path = req_path.split('?', 1)[0].split('#', 1)[0]
    if not path or path == '/':
        path = '/index.html'
    parts = []
    for part in path.split('/'):
        if not part or part == '.':
            continue
        if part == '..':
            continue
        parts.append(part)
    result = WEB_ROOT
    for part in parts:
        result = result + '/' + part
    return result


def file_exists(path: str) -> bool:
    """Return True if path exists and is a file (not a directory)."""
    try:
        return (os.stat(path)[0] & 0x4000) == 0
    except OSError:
        return False


def get_mime(path: str) -> str:
    """Return the MIME type for the given path, or application/octet-stream if unknown."""
    dot = path.rfind('.')
    return MIME.get(path[dot:].lower(), 'application/octet-stream') if dot != -1 else 'application/octet-stream'


def send_all(sock, data: bytes):
    """Send all bytes, retrying on partial sends (MicroPython send() may be short)."""
    pos = 0
    retries = 0
    total = len(data)
    while pos < total:
        try:
            sent = sock.send(data[pos:])
            if sent is None:
                sent = 0
            if sent > 0:
                pos += sent
                retries = 0
                continue
        except OSError:
            pass

        retries += 1
        if retries > 2000:
            raise OSError('send_all timeout')
        time.sleep(0.002)


def send_redirect(sock, location: str):
    """Send a 302 redirect to the given location."""
    send_all(sock, (
        'HTTP/1.1 302 Found\r\n'
        'Connection: close\r\n'
        'Location: {}\r\n'
        'Content-Length: 0\r\n'
        '\r\n'
    ).format(location).encode())


def send_file(sock, path: str):
    """Send the contents of the given file."""
    try:
        size = os.stat(path)[6]
        send_all(sock, (
            'HTTP/1.1 200 OK\r\n'
            'Connection: close\r\n'
            'Content-Type: {}\r\n'
            'Content-Length: {}\r\n'
            'Cache-Control: max-age=3600\r\n'
            '\r\n'
        ).format(get_mime(path), size).encode())
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(2048)
                if not chunk:
                    break
                send_all(sock, chunk)
    except OSError:
        send_all(sock, b'HTTP/1.1 404 Not Found\r\nConnection: close\r\nContent-Length: 9\r\n\r\nNot found')


def send_error(sock, status: str, msg: str):
    """Send an HTTP error response with the given status and message."""
    body = msg.encode()
    send_all(sock, (
        'HTTP/1.1 {}\r\n'
        'Connection: close\r\n'
        'Content-Type: text/plain; charset=utf-8\r\n'
        'Content-Length: {}\r\n'
        '\r\n'
    ).format(status, len(body)).encode() + body)


# ─────────────────────────────────────────────────────────────────────────────
# HTTP request handler
# ─────────────────────────────────────────────────────────────────────────────

def handle_request(client):
    """Handle an incoming HTTP request."""
    try:
        line = client.readline() #— read the request line (e.g. "GET /path HTTP/1.1")
        if not line:
            # No data received (e.g. client disconnected immediately)
            return
        try:
            # Decode the request line as UTF-8 and strip whitespace; if it fails, just ignore the request
            line = line.decode('utf-8').strip()
        except Exception:
            # Invalid request line encoding; ignore the request
            return

        # Drain remaining headers
        while True:
            # Read and discard header lines until we reach an empty line (end of headers)
            h = client.readline()
            if not h or h == b'\r\n':
                break
        # Parse the request line into method and path 
        parts = line.split(' ')
        # We expect at least 2 parts: method and path (e.g. "GET /index.html"); if not, it's a bad request
        if len(parts) < 2:
            send_error(client, '400 Bad Request', 'Bad request')
            return
        print('[HTTP] Request:', line)
        method   = parts[0] #— e.g. "GET"
        full_path = parts[1] #— e.g. "/index.html?foo=1"
        req_path  = full_path.split('?', 1)[0] #— e.g. "/index.html" (without query string)
        
        # Only support GET and HEAD methods; if it's something else (e.g. POST), return 405 Method Not Allowed
        if method not in ('GET', 'HEAD'):
            send_error(client, '405 Method Not Allowed', 'Method not allowed')
            return

        # Intercept OS captive-portal probes in AP mode and serve index directly.
        # Some mobile stacks do not reliably follow redirects during captive checks.
        if mode == 'AP' and req_path in PROBE_PATHS:
            print('[HTTP] Probe:', req_path, '→ index.html')
            target = WEB_ROOT + '/index.html'
            if method == 'HEAD':
                try:
                    size = os.stat(target)[6]
                    send_all(client, (
                        'HTTP/1.1 200 OK\r\nConnection: close\r\n'
                        'Content-Type: {}\r\nContent-Length: {}\r\n\r\n'
                    ).format(get_mime(target), size).encode())
                except OSError:
                    send_error(client, '404 Not Found', 'Not found')
            else:
                send_file(client, target)
            return

        # Map the requested path to a filesystem path under the web root, ensuring it doesn't escape the web root
        target = safe_path(full_path)
        if not file_exists(target):
            target = WEB_ROOT + '/index.html'
        # If the target file doesn't exist, return 404 Not Found
        if method == 'HEAD':
            try:
                size = os.stat(target)[6]
                send_all(client, (
                    'HTTP/1.1 200 OK\r\nConnection: close\r\n'
                    'Content-Type: {}\r\nContent-Length: {}\r\n\r\n'
                ).format(get_mime(target), size).encode())
            except OSError:
                send_error(client, '404 Not Found', 'Not found')
            return
        # If the target file exists, send it with a 200 OK response
        send_file(client, target)
    # Catch any unexpected exceptions and return a 500 Internal Server Error response; if sending the error fails, just ignore it
    except Exception as exc:
        print('[HTTP] Handler error:', exc)
        try:
            send_error(client, '500 Internal Server Error', str(exc))
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Async HTTP server
# ─────────────────────────────────────────────────────────────────────────────

async def http_server():
    addr   = socket.getaddrinfo('0.0.0.0', PORT)[0][-1] # — bind to all interfaces on the specified port
    srv    = socket.socket() # — create a TCP socket
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # — allow reuse of local addresses
    srv.bind(addr) # — bind the socket to the address
    srv.listen(5) # — start listening for incoming connections (backlog of 5)
    srv.setblocking(False) # — set the socket to non-blocking mode so we can use it with asyncio
    print('[HTTP] Serving on http://{}:{}'.format(server_ip, PORT)) 
    print('[HTTP] Mode:', mode) 

    while True:
        handled = False
        try:
            client, _ = srv.accept()
            handled = True
            try:
                client.setblocking(True)
                client.settimeout(5)
                handle_request(client)
            finally:
                client.close()
        except OSError:
            pass
        if handled:
            await asyncio.sleep_ms(1)
        else:
            await asyncio.sleep_ms(20)

# ─────────────────────────────────────────────────────────────────────────────
# OLED display
# ─────────────────────────────────────────────────────────────────────────────

def setup_display():
    i2c = I2C(0, scl=Pin(1), sda=Pin(0), freq=400000)
    oled = SSD1306_I2C(128, 64, i2c, addr=0x3C)
    oled.text('ANCS Pico W', 0, 0)
    oled.text('Mode: ' + mode, 0, 10)
    oled.text('IP: ' + server_ip, 0, 20)
    oled.show()

# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print('[BOOT] Firmware:', FW_VERSION)
    boot_network()
    setup_display()
    tasks = [asyncio.create_task(http_server())]
    if mode == 'AP':
        tasks.append(asyncio.create_task(dns_server()))
    await asyncio.gather(*tasks)


asyncio.run(main())
