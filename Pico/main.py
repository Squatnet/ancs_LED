import network
import socket
import time
import os

SSID = 'BTB-PJCH9N'
PASSWORD = 'NnXeCa3MHpbrNV'
PORT = 80
WEB_ROOT = 'www'

MIME_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.ico': 'image/x-icon',
    '.webp': 'image/webp',
    '.txt': 'text/plain; charset=utf-8',
    '.map': 'application/json; charset=utf-8',
}


def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return wlan.ifconfig()[0]

    wlan.connect(ssid, password)
    wait_seconds = 20
    while wait_seconds > 0 and not wlan.isconnected():
        time.sleep(1)
        wait_seconds -= 1

    if not wlan.isconnected():
        raise RuntimeError('Wi-Fi connection failed')

    return wlan.ifconfig()[0]


def safe_join(root, req_path):
    path = req_path.split('?', 1)[0].split('#', 1)[0]
    if path == '/' or path == '':
        path = '/index.html'

    parts = []
    for part in path.split('/'):
        if not part or part == '.':
            continue
        if part == '..':
            continue
        parts.append(part)

    candidate = root
    for part in parts:
        candidate = candidate + '/' + part
    return candidate


def file_exists(path):
    try:
        mode = os.stat(path)[0]
        return (mode & 0x4000) == 0
    except OSError:
        return False


def get_content_type(path):
    dot = path.rfind('.')
    if dot == -1:
        return 'application/octet-stream'
    ext = path[dot:].lower()
    return MIME_TYPES.get(ext, 'application/octet-stream')


def send_headers(client, status, content_type, content_length=None):
    client.send('HTTP/1.1 ' + status + '\r\n')
    client.send('Connection: close\r\n')
    client.send('Content-Type: ' + content_type + '\r\n')
    if content_length is not None:
        client.send('Content-Length: ' + str(content_length) + '\r\n')
    client.send('\r\n')


def send_file(client, path):
    try:
        size = os.stat(path)[6]
        send_headers(client, '200 OK', get_content_type(path), size)
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(1024)
                if not chunk:
                    break
                client.send(chunk)
    except OSError:
        body = b'Not found'
        send_headers(client, '404 Not Found', 'text/plain; charset=utf-8', len(body))
        client.send(body)


def serve():
    ip = connect_wifi(SSID, PASSWORD)
    print('Connected to Wi-Fi, IP:', ip)

    address = socket.getaddrinfo('0.0.0.0', PORT)[0][-1]
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(address)
    server.listen(5)
    print('Serving on http://' + ip + ':' + str(PORT))

    while True:
        client, _ = server.accept()
        try:
            request_line = client.readline()
            if not request_line:
                client.close()
                continue

            try:
                request_line = request_line.decode('utf-8')
            except UnicodeError:
                request_line = ''

            while True:
                header = client.readline()
                if not header or header == b'\r\n':
                    break

            parts = request_line.split(' ')
            if len(parts) < 2:
                body = b'Bad request'
                send_headers(client, '400 Bad Request', 'text/plain; charset=utf-8', len(body))
                client.send(body)
                client.close()
                continue

            method = parts[0]
            req_path = parts[1]

            if method not in ('GET', 'HEAD'):
                body = b'Method not allowed'
                send_headers(client, '405 Method Not Allowed', 'text/plain; charset=utf-8', len(body))
                if method != 'HEAD':
                    client.send(body)
                client.close()
                continue

            target = safe_join(WEB_ROOT, req_path)
            if not file_exists(target):
                target = WEB_ROOT + '/index.html'

            if method == 'HEAD':
                try:
                    size = os.stat(target)[6]
                    send_headers(client, '200 OK', get_content_type(target), size)
                except OSError:
                    body = b'Not found'
                    send_headers(client, '404 Not Found', 'text/plain; charset=utf-8', len(body))
                client.close()
                continue

            send_file(client, target)
        except Exception as exc:
            try:
                body = ('Server error: ' + str(exc)).encode('utf-8')
                send_headers(client, '500 Internal Server Error', 'text/plain; charset=utf-8', len(body))
                client.send(body)
            except Exception:
                pass
        finally:
            client.close()


serve()