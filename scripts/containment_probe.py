import json
import socket
import sys

config = json.loads(sys.argv[1])
timeout = 2
result = {"tcp": {}, "dns": {}, "names": {}, "bridge_request": {}}


def _name(exc: BaseException) -> str:
    return type(exc).__name__


def tcp(host: str, port: int) -> str:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
    except Exception as exc:
        return _name(exc)
    else:
        return "open"
    finally:
        sock.close()


def udp_dns(ip: str) -> str:
    query = (
        b"\xaa\xaa\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01"
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(query, (ip, 53))
        data, _addr = sock.recvfrom(512)
    except Exception as exc:
        return _name(exc)
    finally:
        sock.close()
    if len(data) < 12:
        return f"response:{len(data)}"
    answers = int.from_bytes(data[6:8], "big")
    if answers == 0:
        return "no_answer"
    return f"answers:{answers}"


for host, port in config.get("tcp", []):
    result["tcp"][f"{host}:{port}"] = tcp(host, int(port))
for ip in config.get("dns", []):
    result["dns"][ip] = udp_dns(ip)
for name in config.get("names", []):
    try:
        result["names"][name] = [item[4][0] for item in socket.getaddrinfo(name, 80)]
    except Exception as exc:
        result["names"][name] = _name(exc)


def read_http(sock: socket.socket) -> str:
    chunks = []
    while True:
        try:
            piece = sock.recv(4096)
        except socket.timeout:
            break
        if not piece:
            break
        chunks.append(piece)
        blob = b"".join(chunks)
        marker = blob.find(b"\r\n\r\n")
        if marker < 0:
            continue
        head = blob[:marker]
        body = blob[marker + 4 :]
        length = None
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                length = int(line.split(b":", 1)[1].strip())
        if length is None or len(body) >= length:
            break
    return b"".join(chunks).decode("utf-8", "replace")[:500]


bridge = config.get("bridge")
if bridge:
    raw = (
        "GET http://1.1.1.1/login HTTP/1.1\r\nHost: 1.1.1.1\r\nConnection: close\r\n\r\n"
    ).encode()
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((bridge["ip"], int(bridge["port"])))
        sock.sendall(raw)
        result["bridge_request"]["absolute"] = read_http(sock)
    except Exception as exc:
        result["bridge_request"]["absolute"] = _name(exc)
    finally:
        sock.close()
    connect_req = ("CONNECT 1.1.1.1:443 HTTP/1.1\r\nHost: 1.1.1.1:443\r\n\r\n").encode()
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((bridge["ip"], int(bridge["port"])))
        sock.sendall(connect_req)
        result["bridge_request"]["connect"] = read_http(sock)
    except Exception as exc:
        result["bridge_request"]["connect"] = _name(exc)
    finally:
        sock.close()

print(json.dumps(result))
