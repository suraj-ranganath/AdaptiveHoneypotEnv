"""Target and bridge have no path to the host, external DNS, or the internet."""

from __future__ import annotations

import json
import socket
import threading

from adaptivehoneypotenv.deployment import Deployment, EpisodeTarget

_PROBE = r"""
import json, socket, sys

config = json.loads(sys.argv[1])
timeout = 2
result = {"tcp": {}, "dns": {}, "names": {}, "bridge_request": {}}

def tcp(host, port):
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return "open"
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    finally:
        sock.close()

def udp_dns(ip):
    query = (
        b"\xaa\xaa\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
        b"\x07example\x03com\x00\x00\x01\x00\x01"
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(query, (ip, 53))
        data, _addr = sock.recvfrom(512)
        if len(data) < 12:
            return f"response:{len(data)}"
        answers = int.from_bytes(data[6:8], "big")
        if answers == 0:
            return "no_answer"
        return f"answers:{answers}"
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    finally:
        sock.close()

for host, port in config.get("tcp", []):
    result["tcp"][f"{host}:{port}"] = tcp(host, port)
for ip in config.get("dns", []):
    result["dns"][ip] = udp_dns(ip)
for name in config.get("names", []):
    try:
        result["names"][name] = [item[4][0] for item in socket.getaddrinfo(name, 80)]
    except Exception as exc:
        result["names"][name] = f"{type(exc).__name__}: {exc}"

def read_http(sock):
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
        "GET http://1.1.1.1/login HTTP/1.1\r\n"
        "Host: 1.1.1.1\r\n"
        "Connection: close\r\n\r\n"
    ).encode()
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((bridge["ip"], bridge["port"]))
        sock.sendall(raw)
        result["bridge_request"]["absolute"] = read_http(sock)
    except Exception as exc:
        result["bridge_request"]["absolute"] = f"{type(exc).__name__}: {exc}"
    finally:
        sock.close()
    connect_req = (
        "CONNECT 1.1.1.1:443 HTTP/1.1\r\n"
        "Host: 1.1.1.1:443\r\n\r\n"
    ).encode()
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((bridge["ip"], bridge["port"]))
        sock.sendall(connect_req)
        result["bridge_request"]["connect"] = read_http(sock)
    except Exception as exc:
        result["bridge_request"]["connect"] = f"{type(exc).__name__}: {exc}"
    finally:
        sock.close()

print(json.dumps(result))
"""


def _blocked(detail: str) -> bool:
    lowered = detail.lower()
    if lowered == "open" or lowered.startswith("response:"):
        return False
    if "refused" in lowered:
        return False
    return True


def _run_probe(
    deployment: Deployment, episode: EpisodeTarget, config: dict, container: str
) -> dict:
    completed = deployment.admin_exec(
        episode,
        ["python3", "-c", _PROBE, json.dumps(config)],
        container=container,
    )
    assert completed.exit_code == 0, completed.stderr.decode()
    return json.loads(completed.stdout.decode())


def test_target_external_dns_tcp_and_host_access_blocked(
    deployment: Deployment, episode: EpisodeTarget
) -> None:
    accepted: list[tuple[str, int]] = []
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("0.0.0.0", 0))
    listener.listen(8)
    listener.settimeout(0.5)
    host_port = listener.getsockname()[1]

    def accept_loop() -> None:
        while True:
            try:
                client, addr = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            accepted.append((addr[0], addr[1]))
            client.close()

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()
    try:
        gateway = deployment.gateway_ipv4(episode)
        bridge_ip = deployment.container_ipv4(episode, "bridge")
        target_probe = _run_probe(
            deployment,
            episode,
            {
                "tcp": [
                    ["1.1.1.1", 443],
                    ["1.1.1.1", 80],
                    ["8.8.8.8", 53],
                    ["8.8.8.8", 443],
                    [gateway, host_port],
                    [gateway, 2375],
                    ["172.17.0.1", host_port],
                    ["2606:4700:4700::1111", 443],
                ],
                "dns": ["8.8.8.8", "1.1.1.1", "127.0.0.11"],
                "names": ["example.com", "host.docker.internal"],
                "bridge": {"ip": bridge_ip, "port": 8080},
            },
            "target",
        )
        bridge_probe = _run_probe(
            deployment,
            episode,
            {
                "tcp": [["1.1.1.1", 443], ["8.8.8.8", 53], [gateway, host_port]],
                "dns": ["8.8.8.8", "1.1.1.1"],
                "names": ["example.com", "host.docker.internal"],
            },
            "bridge",
        )
    finally:
        listener.close()

    assert accepted == []
    for label, report in (("target", target_probe), ("bridge", bridge_probe)):
        for destination, detail in report["tcp"].items():
            assert _blocked(detail), f"{label} tcp {destination} -> {detail}"
        for resolver, detail in report["dns"].items():
            assert _blocked(detail), f"{label} dns {resolver} -> {detail}"
        for name, detail in report["names"].items():
            assert isinstance(detail, str), f"{label} resolved {name} to {detail}"
            assert _blocked(detail), f"{label} name {name} -> {detail}"

    absolute = target_probe["bridge_request"]["absolute"]
    connect = target_probe["bridge_request"]["connect"]
    assert "unknown_destination" in absolute
    assert "unknown_destination" in connect
    assert "1.1.1.1" not in absolute.split("\r\n\r\n", 1)[-1]

    facts = deployment.containment_facts(episode)
    for role in ("target", "bridge"):
        item = facts[role]
        assert item["port_bindings"] in (None, {})
        assert "docker.sock" not in " ".join(item["mount_sources"] + item["binds"])
