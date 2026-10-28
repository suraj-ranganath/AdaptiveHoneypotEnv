"""Bridge rejects redirects, foreign destinations, control plane, and role headers."""

from __future__ import annotations

from adaptivehoneypotenv.contracts.tools import ToolProfile, classify_service_request
from adaptivehoneypotenv.deployment import BODY_LIMIT, Deployment, EpisodeTarget

_REDIRECT_UPSTREAM = """
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(302)
        self.send_header("Location", "http://1.1.1.1/exfil")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        body = b"X" * 20000
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return

ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
"""


def test_http_redirect_unknown_destination_and_control_plane_rejected(
    deployment: Deployment, episode: EpisodeTarget
) -> None:
    actor = deployment.actor_client(episode)
    setup = deployment.setup_client(episode)

    absolute = actor.request(
        "POST",
        "/login",
        raw_target="http://example.com/login",
        json_body={"email": "a@example.com", "password": "x"},
    )
    assert absolute.status_code == 400
    assert absolute.json()["error"] == "unknown_destination"

    scheme_relative = actor.request(
        "GET",
        "/get_secret",
        raw_target="//example.com/get_secret",
    )
    assert scheme_relative.status_code == 400
    assert scheme_relative.json()["error"] == "unknown_destination"

    host = actor.request(
        "POST",
        "/login",
        json_body={"email": "a@example.com", "password": "x"},
        headers={"Host": "evil.example"},
    )
    assert host.status_code == 400
    assert host.json()["error"] == "host_header_rejected"

    forwarded = setup.request(
        "POST",
        "/register",
        json_body={
            "email": "proxy@example.com",
            "username": "proxy_user",
            "password": "proxy-password",
        },
        headers={"X-Forwarded-For": "203.0.113.5"},
    )
    assert forwarded.status_code == 400
    assert forwarded.json()["error"] == "proxy_header_rejected"
    created = setup.register("proxy@example.com", "proxy_user", "proxy-password")
    assert created.status_code == 201, created.body

    for raw_target in (
        "/maintenance",
        "/admin",
        "/controller",
        "/internal",
        "/backup",
        "/restore",
        "/metrics",
        "/actor/docs",
        "/actor/openapi.json",
        "/setup/debug",
    ):
        response = actor.request("POST", "/login", raw_target=raw_target)
        assert response.status_code == 404, raw_target
        assert response.json()["error"] == "control_plane_rejected"

    for path in ("/admin", "/maintenance", "/controller", "/internal", "/login"):
        decision = classify_service_request("POST", path, profile=ToolProfile.malicious)
        if path == "/login":
            assert decision.allowed is True
            continue
        assert decision.allowed is False
        assert decision.reason == "control_plane"
        response = actor.request("POST", "/login", raw_target=path)
        assert response.status_code == 404
        assert response.json()["error"] == "control_plane_rejected"

    oversized = actor.request("POST", "/login", raw_body=b"a" * (BODY_LIMIT + 1))
    assert oversized.status_code == 413
    assert oversized.json()["error"] == "body_limit_exceeded"

    probe = deployment.open_policy_probe(
        upstream_command=["python3", "-c", _REDIRECT_UPSTREAM],
        upstream_port=8080,
    )
    try:
        probe_actor = deployment.actor_client(probe)
        redirected = probe_actor.request(
            "POST",
            "/login",
            json_body={"email": "a@example.com", "password": "x"},
        )
        assert redirected.status_code == 502, redirected.body
        assert redirected.json()["error"] == "redirect_rejected"
        assert "location" not in redirected.headers
        assert b"1.1.1.1" not in redirected.body

        limited = probe_actor.request("GET", "/get_secret", query={"username": "anyone"})
        assert limited.status_code == 502, limited.body
        assert limited.json()["error"] == "response_limit_exceeded"
        assert b"XXXX" not in limited.body
    finally:
        deployment.destroy(probe)


def test_role_headers_cannot_impersonate_controller(
    deployment: Deployment, episode: EpisodeTarget
) -> None:
    actor = deployment.actor_client(episode)
    setup = deployment.setup_client(episode)

    role_only = setup.request(
        "POST",
        "/register",
        authenticate=False,
        json_body={
            "email": "role@example.com",
            "username": "role_user",
            "password": "role-password",
        },
        headers={"AgentEnv-Role": "controller"},
    )
    assert role_only.status_code == 401
    assert role_only.json()["error"] == "controller_token_required"

    bearer_is_not_bridge_auth = setup.request(
        "POST",
        "/register",
        authenticate=False,
        json_body={
            "email": "role@example.com",
            "username": "role_user",
            "password": "role-password",
        },
        headers={
            "Authorization": f"Bearer {episode.controller_token}",
            "X-Role": "controller",
        },
    )
    assert bearer_is_not_bridge_auth.status_code == 401

    widened = actor.request(
        "POST",
        "/register",
        json_body={
            "email": "role@example.com",
            "username": "role_user",
            "password": "role-password",
        },
        headers={"AgentEnv-Role": "controller", "X-Profile": "benign"},
    )
    assert widened.status_code == 403
    assert widened.json()["error"] == "profile_rejected"
    created = setup.register("role@example.com", "role_user", "role-password")
    assert created.status_code == 201, created.body

    maintenance = actor.request(
        "POST",
        "/login",
        raw_target="/maintenance",
        headers={"AgentEnv-Role": "controller"},
    )
    assert maintenance.status_code == 404
    assert maintenance.json()["error"] == "control_plane_rejected"


def test_benign_profile_can_register_and_malicious_profile_cannot(
    deployment: Deployment,
) -> None:
    benign = deployment.create_episode_target(profile="benign")
    try:
        response = deployment.actor_client(benign).register(
            "benign@example.com", "benign_user", "benign-password"
        )
        assert response.status_code == 201, response.body
    finally:
        deployment.destroy(benign)

    malicious = deployment.create_episode_target(profile="malicious")
    try:
        response = deployment.actor_client(malicious).register(
            "malicious@example.com", "malicious_user", "malicious-password"
        )
        assert response.status_code == 403
        setup = deployment.setup_client(malicious)
        created = setup.register("malicious@example.com", "malicious_user", "malicious-password")
        assert created.status_code == 201, created.body
        hidden = deployment.actor_client(malicious).request("GET", "/get_secret")
        assert hidden.status_code in {400, 401, 403}
    finally:
        deployment.destroy(malicious)
