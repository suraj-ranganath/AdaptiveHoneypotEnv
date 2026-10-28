"""Trusted episode launcher for the SecretStorage target and fixed bridge.

Compiler and reset call ``create_episode_target``, ``backup``, ``restore``,
``destroy``, and ``setup_client``. The bridge endpoint and controller token
live on the returned handle. A created episode carries an ``EpisodeStarted``
envelope and ``source_pins`` reports the frozen ``SourcePins`` fields. A full
live manifest stays with the runner: ``max_cost_usd`` is an operator input.

Docker is driven through the Engine API with argument arrays. The maintenance
helper is started the same way and is not an HTTP route. No container receives
the Docker socket.

Docker does not install host port mappings for ``internal`` networks, and a
second NIC would give the bridge a default route. The launcher therefore
binds ``127.0.0.1`` and relays bytes to the bridge container's address.
Per-network firewall rules drop new connections from that bridge to the host.
``internal`` alone still delivers those packets to the bridge gateway.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
from dataclasses import dataclass, replace
from http.client import HTTPConnection
from pathlib import Path
from typing import Any, Literal

import docker
from docker.errors import (
    APIError,
    BuildError,
    ContainerError,
    DockerException,
    ImageNotFound,
    NotFound,
)

from adaptivehoneypotenv.contracts.events import (
    EpisodeStarted,
    EventStatus,
    Principal,
    compute_event_id,
    project_operator,
)
from adaptivehoneypotenv.contracts.manifest import SourcePins

TARGET_IMAGE = "adaptivehoneypotenv-target:gate-a"
BRIDGE_IMAGE = "adaptivehoneypotenv-bridge:gate-a"
BASE_IMAGE = (
    "python:3.12-slim@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b"
)
BODY_LIMIT = 16384
RUN_USER = "65532:65532"
PROBE_USER = "65534:65534"
TOKEN_HEADER = "X-Controller-Token"
HONEYVAL_GIT_SHA = "86272d8d1fb4b3090037561cc31b28dc8a8350f8"
AGENTENV_GIT_SHA = "666c26a586c9118599352c7caa52f53d2e89fb62"
_EPISODE_ID = re.compile(r"^ep_[A-Za-z0-9_-]{8,64}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_IFACE = re.compile(r"^br-[0-9a-f]{12}$")
_FIREWALL_BINARIES = frozenset({"iptables", "iptables-legacy", "ip6tables", "ip6tables-legacy"})

TARGET_TMPFS = {
    "/run/state": "rw,nosuid,nodev,noexec,size=64m,uid=65532,gid=65532",
    "/tmp": "rw,nosuid,nodev,noexec,size=16m,uid=65532,gid=65532",
}
BRIDGE_TMPFS = {
    "/tmp": "rw,nosuid,nodev,noexec,size=16m,uid=65532,gid=65532",
}
PROBE_TMPFS = {
    "/tmp": "rw,nosuid,nodev,noexec,size=16m,uid=65534,gid=65534",
}


class DeploymentError(RuntimeError):
    """The launcher could not keep the episode's containment contract."""


class MaintenanceError(DeploymentError):
    """Backup or restore did not complete. The caller must invalidate the episode."""


@dataclass(frozen=True)
class EpisodeTarget:
    """Controller handle for one episode. ``repr`` omits the token."""

    episode_id: str
    profile: str
    bridge_endpoint: str
    controller_token: str
    target_container_id: str
    bridge_container_id: str
    network_id: str
    started_event: EpisodeStarted | None = None

    def __repr__(self) -> str:
        return (
            "EpisodeTarget("
            f"episode_id={self.episode_id!r}, profile={self.profile!r}, "
            f"bridge_endpoint={self.bridge_endpoint!r})"
        )


@dataclass(frozen=True)
class ServiceResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: bytes
    stderr: bytes


@dataclass
class _Runtime:
    episode_id: str
    kind: str
    target: Any
    bridge: Any
    network: Any
    relay: LoopbackRelay | None
    lock: threading.RLock
    iface: str
    firewall: list[tuple[str, list[str]]]


class LoopbackRelay:
    """Byte pipe from 127.0.0.1 to one fixed container address."""

    def __init__(self, upstream_host: str, upstream_port: int) -> None:
        ipaddress.IPv4Address(upstream_host)
        if not 1 <= upstream_port <= 65535:
            raise DeploymentError("upstream port is out of range")
        self._upstream = (upstream_host, upstream_port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(32)
        self._sock.settimeout(0.2)
        self._closed = threading.Event()
        self._thread = threading.Thread(
            target=self._accept_loop, name="ahe-loopback-relay", daemon=True
        )
        self._thread.start()

    @property
    def endpoint(self) -> str:
        host, port = self._sock.getsockname()
        if host != "127.0.0.1":
            raise DeploymentError("relay is not bound to loopback")
        return f"http://127.0.0.1:{port}"

    def close(self) -> None:
        self._closed.set()
        try:
            self._sock.close()
        except OSError:
            pass

    def _accept_loop(self) -> None:
        while not self._closed.is_set():
            try:
                client, _addr = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            threading.Thread(
                target=self._serve, args=(client,), name="ahe-relay-conn", daemon=True
            ).start()

    def _serve(self, client: socket.socket) -> None:
        upstream: socket.socket | None = None
        try:
            upstream = socket.create_connection(self._upstream, timeout=5)
            client.settimeout(30)
            upstream.settimeout(30)
            left = threading.Thread(target=_splice, args=(client, upstream), daemon=True)
            right = threading.Thread(target=_splice, args=(upstream, client), daemon=True)
            left.start()
            right.start()
            left.join()
            right.join()
        except OSError:
            pass
        finally:
            for sock in (client, upstream):
                if sock is None:
                    continue
                try:
                    sock.close()
                except OSError:
                    pass


def _splice(source: socket.socket, destination: socket.socket) -> None:
    try:
        while True:
            chunk = source.recv(16384)
            if not chunk:
                break
            destination.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            destination.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class ServiceClient:
    """HTTP client for one bridge route prefix. Holds the episode quiescence lock."""

    def __init__(
        self,
        endpoint: str,
        token: str,
        prefix: str,
        lock: threading.RLock,
    ) -> None:
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
            raise DeploymentError("bridge endpoint must be http://127.0.0.1:<port>")
        self._host = parsed.hostname
        self._port = parsed.port
        self._token = token
        self._prefix = prefix
        self._lock = lock

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        json_body: Any = None,
        raw_body: bytes | None = None,
        headers: dict[str, str] | None = None,
        authenticate: bool = True,
        raw_target: str | None = None,
    ) -> ServiceResponse:
        if raw_target is None:
            if not path.startswith("/"):
                raise DeploymentError("path must start with /")
            target = self._prefix + path
            if query:
                target += "?" + urllib.parse.urlencode(query)
        else:
            target = raw_target
        body = raw_body
        header_map = {}
        if authenticate:
            header_map[TOKEN_HEADER] = self._token
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            header_map["Content-Type"] = "application/json"
        if headers:
            header_map.update(headers)
        if body is None:
            body = b""
        header_map["Content-Length"] = str(len(body))
        header_map["Connection"] = "close"
        with self._lock:
            connection = HTTPConnection(self._host, self._port, timeout=10)
            try:
                connection.request(method, target, body=body, headers=header_map)
                upstream = connection.getresponse()
                payload = upstream.read(BODY_LIMIT + 64)
                response_headers = {key.lower(): value for key, value in upstream.getheaders()}
                return ServiceResponse(upstream.status, response_headers, payload)
            finally:
                connection.close()

    def register(self, email: str, username: str, password: str) -> ServiceResponse:
        return self.request(
            "POST",
            "/register",
            json_body={"email": email, "username": username, "password": password},
        )

    def login(self, email: str, password: str) -> ServiceResponse:
        return self.request(
            "POST",
            "/login",
            json_body={"email": email, "password": password},
        )

    def set_secret(self, username: str, secret: str, token: str) -> ServiceResponse:
        return self.request(
            "POST",
            "/set_secret",
            json_body={"username": username, "secret": secret},
            headers={"Authorization": f"Bearer {token}"},
        )

    def get_secret(self, username: str, token: str) -> ServiceResponse:
        return self.request(
            "GET",
            "/get_secret",
            query={"username": username},
            headers={"Authorization": f"Bearer {token}"},
        )


def _argv(argv: list[str]) -> list[str]:
    if not argv or not all(isinstance(part, str) for part in argv):
        raise DeploymentError("command must be an argument array")
    if any("\x00" in part for part in argv):
        raise DeploymentError("command contains NUL")
    return argv


def _which_tool(name: str) -> str | None:
    """Find a firewall binary. sbin is often absent from PATH."""
    search = os.environ.get("PATH", "") + ":/usr/sbin:/sbin"
    found = shutil.which(name, path=search)
    if found:
        return found
    fallback = "/usr/sbin/" + name
    if os.path.isfile(fallback) and os.access(fallback, os.X_OK):
        return fallback
    return None


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    command = _argv(argv)
    if command[0] in _FIREWALL_BINARIES:
        binary = _which_tool(command[0])
        if binary is None:
            raise DeploymentError(f"{command[0]} is not installed")
        if os.geteuid() != 0:
            command = ["sudo", "-n", binary, *command[1:]]
        else:
            command = [binary, *command[1:]]
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _iface_name(network_id: str) -> str:
    iface = "br-" + network_id[:12]
    if not _IFACE.fullmatch(iface):
        raise DeploymentError("network id is not a docker bridge id")
    return iface


def _install_firewall(iface: str) -> list[tuple[str, list[str]]]:
    if not _IFACE.fullmatch(iface):
        raise DeploymentError("refusing to change firewall rules for this interface")
    installed: list[tuple[str, list[str]]] = []
    drop_new = ["-I", "INPUT", "-i", iface, "-m", "conntrack", "--ctstate", "NEW", "-j", "DROP"]
    allow_peers = ["-I", "FORWARD", "-i", iface, "-o", iface, "-j", "ACCEPT"]
    rules = [
        ("iptables", drop_new),
        ("iptables", allow_peers),
    ]
    if _which_tool("iptables-legacy"):
        rules.extend(
            [
                ("iptables-legacy", drop_new),
                ("iptables-legacy", allow_peers),
            ]
        )
    for binary in ("ip6tables", "ip6tables-legacy"):
        if _which_tool(binary):
            rules.append((binary, drop_new))
    for binary, insert_args in rules:
        result = _run([binary, *insert_args])
        if result.returncode != 0:
            if binary.startswith("ip6"):
                continue
            _remove_firewall(installed)
            detail = (result.stderr or result.stdout or "").strip()
            raise DeploymentError(f"firewall rule failed ({binary}): {detail}")
        delete_args = ["-D", *insert_args[1:]]
        installed.append((binary, delete_args))
    return installed


def _remove_firewall(rules: list[tuple[str, list[str]]]) -> None:
    for binary, delete_args in reversed(rules):
        _run([binary, *delete_args])


class Deployment:
    """Creates and destroys one isolated SecretStorage episode at a time."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[1]
        self._client = self._connect()
        self._runtimes: dict[str, _Runtime] = {}
        self._build_lock = threading.Lock()
        self._images_ready = False
        self.build_proofs: list[str] = []

    def close(self) -> None:
        for episode_id in list(self._runtimes):
            runtime = self._runtimes.pop(episode_id, None)
            if runtime is not None:
                self._teardown(runtime)

    def ensure_images(self) -> None:
        with self._build_lock:
            if self._images_ready:
                return
            self._ensure_base_image()
            self._ensure_image(TARGET_IMAGE, "docker/target/Dockerfile")
            self._ensure_image(BRIDGE_IMAGE, "docker/bridge/Dockerfile")
            self._prove_passlib()
            self._images_ready = True

    def create_episode_target(
        self,
        *,
        episode_id: str | None = None,
        profile: str = "malicious",
        team: Literal["solo", "trio"] = "trio",
    ) -> EpisodeTarget:
        """Start a fresh process, SQLite file, APP_SECRET, and controller token."""
        if team not in {"solo", "trio"}:
            raise DeploymentError("team must be solo or trio")
        self.ensure_images()
        started_ns = time.monotonic_ns()
        identity = _new_episode_id(episode_id)
        if profile not in {"malicious", "benign"}:
            raise DeploymentError("profile must be malicious or benign")
        app_secret = secrets.token_urlsafe(48)
        token = secrets.token_urlsafe(32)
        if len(app_secret) < 32 or len(token) < 32:
            raise DeploymentError("generated secret is unexpectedly short")
        handle = self._start(
            episode_id=identity,
            profile=profile,
            token=token,
            kind="target",
            target_image=TARGET_IMAGE,
            target_command=None,
            target_env={
                "APP_SECRET": app_secret,
                "HOME": "/tmp",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": "/opt/secretstorage",
            },
            target_user=RUN_USER,
            target_tmpfs=TARGET_TMPFS,
            target_workdir="/run/state",
            target_port=5000,
            mem_limit="256m",
        )
        event = _episode_started(identity, team, started_ns)
        project_operator(event)
        return replace(handle, started_event=event)

    def source_pins(self) -> SourcePins:
        """Image ids and the lockfile hash. Not a full live manifest."""
        self.ensure_images()
        lock_path = self.repo_root / "uv.lock"
        if not lock_path.is_file():
            raise DeploymentError("uv.lock is not in the repository root")
        return SourcePins(
            honeyval_git_sha=HONEYVAL_GIT_SHA,
            agentenv_git_sha=AGENTENV_GIT_SHA,
            target_image_digest=self._image_id(TARGET_IMAGE),
            bridge_image_digest=self._image_id(BRIDGE_IMAGE),
            lock_sha256=hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        )

    def open_policy_probe(
        self,
        *,
        upstream_command: list[str],
        upstream_port: int,
        profile: str = "malicious",
    ) -> EpisodeTarget:
        """Bridge in front of a test-only upstream. Not the compiler API.

        Used to prove redirect and response-limit behavior. The upstream
        command is an argument array on the pinned Python image, attached only
        to the episode's internal network.
        """
        self.ensure_images()
        command = _argv(list(upstream_command))
        return self._start(
            episode_id=_new_episode_id(None),
            profile=profile,
            token=secrets.token_urlsafe(32),
            kind="probe",
            target_image=BASE_IMAGE,
            target_command=command,
            target_env={"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
            target_user=PROBE_USER,
            target_tmpfs=PROBE_TMPFS,
            target_workdir="/tmp",
            target_port=upstream_port,
            mem_limit="128m",
        )

    def setup_client(self, episode: EpisodeTarget) -> ServiceClient:
        """Private setup route. All four SecretStorage operations, controller token."""
        return self._service_client(episode, "/setup")

    def actor_client(self, episode: EpisodeTarget) -> ServiceClient:
        """Actor route. Allows only the episode profile."""
        return self._service_client(episode, "/actor")

    def backup(self, episode: EpisodeTarget) -> None:
        """Snapshot the live SQLite database. Requests on this handle must be idle."""
        self._maintenance(episode, "backup")

    def restore(self, episode: EpisodeTarget) -> None:
        """Restore the snapshot into the running process. Does not restart it."""
        self._maintenance(episode, "restore")

    def destroy(self, episode: EpisodeTarget) -> None:
        runtime = self._runtimes.pop(episode.episode_id, None)
        if runtime is not None:
            self._teardown(runtime)

    def app_pid(self, episode: EpisodeTarget) -> int:
        payload = self._stat(episode)
        return int(payload["pid"])

    def user_count(self, episode: EpisodeTarget) -> int:
        payload = self._stat(episode)
        return int(payload["user_count"])

    def secret_fingerprint(self, episode: EpisodeTarget) -> str:
        result = self.admin_exec(
            episode,
            [
                "python",
                "-c",
                "import hashlib, os; "
                "print(hashlib.sha256(os.environ['APP_SECRET'].encode()).hexdigest())",
            ],
        )
        if result.exit_code != 0:
            raise DeploymentError("could not fingerprint APP_SECRET")
        return result.stdout.decode("ascii").strip()

    def secret_is_strong(self, episode: EpisodeTarget) -> bool:
        script = (
            "import os\n"
            "fallback='super-secret-key-that-should-be-changed-in-production-1234567890abcdef'\n"
            "secret=os.environ.get('APP_SECRET','')\n"
            "print('strong' if secret != fallback and len(secret) >= 32 else 'weak')\n"
        )
        result = self.admin_exec(episode, ["python", "-c", script])
        if result.exit_code != 0:
            raise DeploymentError("could not check APP_SECRET")
        return result.stdout.decode("ascii").strip() == "strong"

    def admin_exec(
        self,
        episode: EpisodeTarget,
        argv: list[str],
        *,
        container: str = "target",
    ) -> ExecResult:
        """Run a fixed argument array inside a container. Not an actor tool."""
        command = _argv(list(argv))
        if container not in {"target", "bridge"}:
            raise DeploymentError("container must be target or bridge")
        runtime = self._runtime(episode)
        chosen = runtime.target if container == "target" else runtime.bridge
        user = RUN_USER if runtime.kind == "target" or container == "bridge" else PROBE_USER
        if runtime.kind == "probe" and container == "target":
            user = PROBE_USER
        completed = chosen.exec_run(command, demux=True, user=user)
        code, output = completed
        stdout, stderr = output if isinstance(output, tuple) else (output, b"")
        return ExecResult(int(code), stdout or b"", stderr or b"")

    def container_ipv4(self, episode: EpisodeTarget, container: str = "target") -> str:
        runtime = self._runtime(episode)
        chosen = runtime.target if container == "target" else runtime.bridge
        chosen.reload()
        networks = chosen.attrs["NetworkSettings"]["Networks"]
        address = networks[runtime.network.name]["IPAddress"]
        return str(ipaddress.IPv4Address(address))

    def gateway_ipv4(self, episode: EpisodeTarget) -> str:
        runtime = self._runtime(episode)
        runtime.network.reload()
        config = runtime.network.attrs["IPAM"]["Config"][0]
        return str(ipaddress.IPv4Address(config["Gateway"]))

    def containment_facts(self, episode: EpisodeTarget) -> dict[str, Any]:
        runtime = self._runtime(episode)
        runtime.target.reload()
        runtime.bridge.reload()
        runtime.network.reload()
        relay_host, relay_port = ("", 0)
        if runtime.relay is not None:
            relay_host, relay_port = runtime.relay._sock.getsockname()
        return {
            "network_internal": bool(runtime.network.attrs.get("Internal")),
            "relay_host": relay_host,
            "relay_port": relay_port,
            "target": _container_facts(runtime.target),
            "bridge": _container_facts(runtime.bridge),
        }

    def _service_client(self, episode: EpisodeTarget, prefix: str) -> ServiceClient:
        runtime = self._runtime(episode)
        return ServiceClient(
            episode.bridge_endpoint,
            episode.controller_token,
            prefix,
            runtime.lock,
        )

    def _start(
        self,
        *,
        episode_id: str,
        profile: str,
        token: str,
        kind: str,
        target_image: str,
        target_command: list[str] | None,
        target_env: dict[str, str],
        target_user: str,
        target_tmpfs: dict[str, str],
        target_workdir: str,
        target_port: int,
        mem_limit: str,
    ) -> EpisodeTarget:
        runtime = _Runtime(
            episode_id=episode_id,
            kind=kind,
            target=None,
            bridge=None,
            network=None,
            relay=None,
            lock=threading.RLock(),
            iface="",
            firewall=[],
        )
        try:
            runtime.network = self._client.networks.create(
                name=f"ahe-n-{episode_id}",
                driver="bridge",
                internal=True,
                check_duplicate=True,
                labels={"ahe.episode": episode_id, "ahe.role": "network"},
            )
            runtime.network.reload()
            runtime.iface = _iface_name(runtime.network.id)
            runtime.firewall = _install_firewall(runtime.iface)
            runtime.target = self._run_container(
                image=target_image,
                name=f"ahe-target-{episode_id}",
                command=target_command,
                environment=target_env,
                user=target_user,
                tmpfs=target_tmpfs,
                working_dir=target_workdir,
                network=runtime.network.name,
                mem_limit=mem_limit,
                nano_cpus=500_000_000,
                labels={"ahe.episode": episode_id, "ahe.role": "target"},
            )
            self._wait_local_port(runtime.target, target_port, user=target_user)
            upstream_host = self._ipv4(runtime.target, runtime.network.name)
            runtime.bridge = self._run_container(
                image=BRIDGE_IMAGE,
                name=f"ahe-bridge-{episode_id}",
                command=None,
                environment={
                    "UPSTREAM_HOST": upstream_host,
                    "UPSTREAM_PORT": str(target_port),
                    "CONTROLLER_TOKEN": token,
                    "PROFILE": profile,
                    "HOME": "/tmp",
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
                user=RUN_USER,
                tmpfs=BRIDGE_TMPFS,
                working_dir=None,
                network=runtime.network.name,
                mem_limit="128m",
                nano_cpus=500_000_000,
                labels={"ahe.episode": episode_id, "ahe.role": "bridge"},
            )
            self._wait_local_port(runtime.bridge, 8080, user=RUN_USER)
            bridge_ip = self._ipv4(runtime.bridge, runtime.network.name)
            runtime.relay = LoopbackRelay(bridge_ip, 8080)
            self._wait_bridge(runtime.relay.endpoint)
            self._runtimes[episode_id] = runtime
            handle = EpisodeTarget(
                episode_id=episode_id,
                profile=profile,
                bridge_endpoint=runtime.relay.endpoint,
                controller_token=token,
                target_container_id=runtime.target.id,
                bridge_container_id=runtime.bridge.id,
                network_id=runtime.network.id,
            )
            return handle
        except Exception:
            self._teardown(runtime)
            raise

    def _maintenance(self, episode: EpisodeTarget, operation: str) -> bytes:
        if operation not in {"backup", "restore", "stat"}:
            raise MaintenanceError("unknown maintenance operation")
        runtime = self._runtime(episode)
        if runtime.kind != "target":
            raise MaintenanceError("maintenance applies only to a SecretStorage target")
        with runtime.lock:
            result = self.admin_exec(
                episode,
                ["python", "/opt/secretstorage/maintenance.py", operation],
            )
        if result.exit_code != 0:
            detail = (result.stderr or result.stdout).decode("utf-8", "replace")[:400]
            raise MaintenanceError(detail or f"{operation} failed")
        return result.stdout

    def _stat(self, episode: EpisodeTarget) -> dict[str, Any]:
        raw = self._maintenance(episode, "stat")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or "pid" not in payload or "user_count" not in payload:
            raise MaintenanceError("stat response is incomplete")
        parsed: dict[str, Any] = {str(key): value for key, value in payload.items()}
        return parsed

    def _runtime(self, episode: EpisodeTarget) -> _Runtime:
        runtime = self._runtimes.get(episode.episode_id)
        if runtime is None:
            raise DeploymentError("episode is not active")
        return runtime

    def _ensure_base_image(self) -> None:
        try:
            self._client.images.get(BASE_IMAGE)
            return
        except ImageNotFound:
            pass
        result = subprocess.run(
            ["docker", "pull", BASE_IMAGE],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[-400:]
            raise DeploymentError(f"could not pull the pinned base image: {detail}")
        try:
            self._client.images.get(BASE_IMAGE)
        except ImageNotFound as exc:
            raise DeploymentError("pinned python base image is not present after pull") from exc

    def _image_id(self, tag: str) -> str:
        try:
            image_id = self._client.images.get(tag).id
        except ImageNotFound as exc:
            raise DeploymentError(f"{tag} is not built") from exc
        if not isinstance(image_id, str) or not _IMAGE_ID.fullmatch(image_id):
            raise DeploymentError(f"{tag} has no sha256 image id")
        return image_id

    def _connect(self) -> Any:
        try:
            client = docker.from_env()
            client.ping()
        except DockerException as exc:
            raise DeploymentError(f"Docker is unavailable: {exc}") from exc
        return client

    def _ensure_image(self, tag: str, dockerfile: str) -> None:
        lines: list[str] = []
        try:
            _image, logs = self._client.images.build(
                path=str(self.repo_root),
                dockerfile=dockerfile,
                tag=tag,
                rm=True,
                pull=False,
            )
            for chunk in logs:
                text = chunk.get("stream") or chunk.get("error") or ""
                if text:
                    lines.append(text)
                    if "passlib-bcrypt login proof ok" in text:
                        self.build_proofs.append(text.strip())
        except BuildError as exc:
            tail = "".join(lines)[-2000:]
            raise DeploymentError(f"image build failed for {tag}: {tail}") from exc

    def _prove_passlib(self) -> None:
        script = (
            "from passlib.context import CryptContext\n"
            "import bcrypt, passlib\n"
            "ctx = CryptContext(schemes=['bcrypt'], deprecated='auto')\n"
            "hashed = ctx.hash('login-proof')\n"
            "assert ctx.verify('login-proof', hashed)\n"
            "assert not ctx.verify('other-password', hashed)\n"
            "print(f'passlib {passlib.__version__} bcrypt {bcrypt.__version__}')\n"
        )
        try:
            output = self._client.containers.run(
                TARGET_IMAGE,
                entrypoint=["python", "-c", script],
                remove=True,
                user=RUN_USER,
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                network_mode="none",
                mem_limit="128m",
                pids_limit=32,
            )
        except ContainerError as exc:
            raise DeploymentError(f"passlib/bcrypt proof failed: {exc.stderr}") from exc
        text = output.decode("utf-8", "replace").strip()
        if "passlib" not in text or "bcrypt" not in text:
            raise DeploymentError("passlib/bcrypt proof produced no version line")
        self.build_proofs.append(text)

    def _run_container(
        self,
        *,
        image: str,
        name: str,
        command: list[str] | None,
        environment: dict[str, str],
        user: str,
        tmpfs: dict[str, str],
        working_dir: str | None,
        network: str,
        mem_limit: str,
        nano_cpus: int,
        labels: dict[str, str],
    ) -> Any:
        sock_in_env = any(
            "docker.sock" in key or "docker.sock" in value for key, value in environment.items()
        )
        if sock_in_env:
            raise DeploymentError("refusing to place docker.sock in the environment")
        options: dict[str, Any] = {
            "name": name,
            "detach": True,
            "user": user,
            "read_only": True,
            "init": True,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "mem_limit": mem_limit,
            "nano_cpus": nano_cpus,
            "pids_limit": 64,
            "tmpfs": tmpfs,
            "environment": environment,
            "network": network,
            "dns": ["127.0.0.1"],
            "dns_opt": ["attempts:1", "timeout:1"],
            "dns_search": [],
            "labels": labels,
        }
        if command is not None:
            options["command"] = command
        if working_dir is not None:
            options["working_dir"] = working_dir
        try:
            return self._client.containers.run(image, **options)
        except APIError as exc:
            raise DeploymentError(f"container start failed for {name}: {exc.explanation}") from exc

    def _wait_local_port(self, container: Any, port: int, *, user: str) -> None:
        script = f"import socket, sys\nsocket.create_connection(('127.0.0.1', {port}), 2).close()\n"
        deadline = time.monotonic() + 40
        last = ""
        while time.monotonic() < deadline:
            container.reload()
            if container.status not in {"created", "running"}:
                logs = _safe_logs(container)
                raise DeploymentError(f"container exited before listening: {logs}")
            completed = container.exec_run(["python", "-c", script], demux=True, user=user)
            code, output = completed
            if code == 0:
                return
            stderr = b""
            if isinstance(output, tuple) and output[1]:
                stderr = output[1]
            last = stderr.decode("utf-8", "replace")[:200]
            time.sleep(0.3)
        logs = _safe_logs(container)
        raise DeploymentError(f"container port {port} did not open: {last} {logs}")

    def _wait_bridge(self, endpoint: str) -> None:
        parsed = urllib.parse.urlsplit(endpoint)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                host = parsed.hostname
                port = parsed.port
                if host is None or port is None:
                    raise DeploymentError("bridge endpoint is not a host and port")
                connection = HTTPConnection(host, port, timeout=2)
                connection.request("GET", "/actor/login", headers={"Connection": "close"})
                response = connection.getresponse()
                response.read()
                connection.close()
                if response.status == 401:
                    return
            except OSError:
                pass
            time.sleep(0.3)
        raise DeploymentError("bridge did not become ready")

    def _ipv4(self, container: Any, network_name: str) -> str:
        container.reload()
        address = container.attrs["NetworkSettings"]["Networks"][network_name]["IPAddress"]
        return str(ipaddress.IPv4Address(address))

    def _teardown(self, runtime: _Runtime) -> None:
        if runtime.relay is not None:
            runtime.relay.close()
        for container in (runtime.bridge, runtime.target):
            if container is None:
                continue
            try:
                container.remove(force=True)
            except (APIError, NotFound):
                pass
        _remove_firewall(runtime.firewall)
        if runtime.network is not None:
            try:
                runtime.network.remove()
            except (APIError, NotFound):
                pass


def _new_episode_id(episode_id: str | None) -> str:
    identity = episode_id or f"ep_{secrets.token_hex(8)}"
    if not _EPISODE_ID.fullmatch(identity):
        raise DeploymentError("episode_id must match ep_ plus 8-64 identifier characters")
    return identity


def _episode_started(
    episode_id: str,
    team: Literal["solo", "trio"],
    started_ns: int,
) -> EpisodeStarted:
    kind: Literal["episode_started"] = "episode_started"
    sequence = 0
    return EpisodeStarted(
        event_id=compute_event_id(episode_id, sequence, kind),
        episode_id=episode_id,
        sequence=sequence,
        round_index=0,
        attempt_index=0,
        world_version=0,
        actor=Principal(role="controller", actor_id="controller"),
        status=EventStatus.ok,
        monotonic_duration_ns=max(0, time.monotonic_ns() - started_ns),
        wall_time_unix_ns=time.time_ns(),
        request_id=f"req_{episode_id}_start",
        kind=kind,
        scenario_id="secret_store_ops/v1",
        catalogue_ordering_version="secret_store_ops/v1.ordering.1",
        team=team,
    )


def _safe_logs(container: Any) -> str:
    try:
        raw = container.logs(tail=40)
    except (APIError, NotFound):
        return ""
    if not isinstance(raw, bytes):
        return ""
    return raw.decode("utf-8", "replace")[-800:]


def _env_names(container: Any) -> list[str]:
    names = []
    for item in container.attrs.get("Config", {}).get("Env") or []:
        names.append(item.split("=", 1)[0])
    return sorted(names)


def _container_facts(container: Any) -> dict[str, Any]:
    host = container.attrs.get("HostConfig") or {}
    mounts = container.attrs.get("Mounts") or []
    binds = host.get("Binds") or []
    sources = [str(mount.get("Source", "")) for mount in mounts]
    ports = container.attrs.get("NetworkSettings", {}).get("Ports")
    return {
        "name": container.name,
        "user": (container.attrs.get("Config") or {}).get("User"),
        "privileged": bool(host.get("Privileged")),
        "readonly_rootfs": bool(host.get("ReadonlyRootfs")),
        "cap_drop": host.get("CapDrop") or [],
        "security_opt": host.get("SecurityOpt") or [],
        "pid_mode": host.get("PidMode") or "",
        "network_mode": host.get("NetworkMode") or "",
        "port_bindings": host.get("PortBindings"),
        "ports": ports,
        "binds": binds,
        "mount_sources": sources,
        "env_names": _env_names(container),
        "memory": host.get("Memory"),
        "nano_cpus": host.get("NanoCpus"),
        "pids_limit": host.get("PidsLimit"),
    }
