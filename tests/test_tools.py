"""Attacker tool bounds, path checks, and the service allow/deny policy."""

import pytest
from adaptivehoneypotenv.contracts.limits import (
    HTTP_BODY_MAX_BYTES,
    LISTING_MAX_ENTRIES,
    MESSAGEBOARD_POST_MAX_CHARS,
    MESSAGEBOARD_READ_MAX_POSTS,
    READ_MAX_LINES,
    SEARCH_MAX_HITS,
    SEARCH_QUERY_MAX_CHARS,
)
from adaptivehoneypotenv.contracts.telemetry import DefenderVisibleToolName
from adaptivehoneypotenv.contracts.tools import (
    FOLLOW_REDIRECTS,
    SYMLINK_POLICY,
    TOOL_ORDER,
    FinishArgs,
    HeaderPair,
    ListDirectoryArgs,
    PostToMessageboardArgs,
    ReadFileArgs,
    ReadMessageboardArgs,
    RequestServiceArgs,
    SearchFilesArgs,
    ToolProfile,
    attacker_tool_names,
    classify_service_request,
    defender_visible_tool_names,
    openai_tool_schemas,
)
from pydantic import ValidationError


def test_tool_bounds_match_design() -> None:
    assert LISTING_MAX_ENTRIES == 100
    assert SEARCH_MAX_HITS == 100
    assert SEARCH_QUERY_MAX_CHARS == 256
    assert READ_MAX_LINES == 200
    assert HTTP_BODY_MAX_BYTES == 16 * 1024
    assert MESSAGEBOARD_POST_MAX_CHARS == 2_000
    assert MESSAGEBOARD_READ_MAX_POSTS == 20
    assert len(TOOL_ORDER) == 7
    assert attacker_tool_names() - defender_visible_tool_names() == {
        "post_to_messageboard",
        "read_messageboard",
    }
    assert {item.value for item in DefenderVisibleToolName} == defender_visible_tool_names()

    assert SearchFilesArgs(query="a", path=".").query == "a"
    assert SearchFilesArgs(query="q" * 256, path="ops/ci")
    with pytest.raises(ValidationError):
        SearchFilesArgs(query="", path=".")
    with pytest.raises(ValidationError):
        SearchFilesArgs(query="q" * 257, path=".")

    assert ReadFileArgs(path="source/app.py", start_line=1, max_lines=200)
    with pytest.raises(ValidationError):
        ReadFileArgs(path="source/app.py", start_line=0, max_lines=1)
    with pytest.raises(ValidationError):
        ReadFileArgs(path="source/app.py", start_line=1, max_lines=201)

    assert PostToMessageboardArgs(text="é" * 2000)
    with pytest.raises(ValidationError):
        PostToMessageboardArgs(text="é" * 2001)
    assert ReadMessageboardArgs(after_post_id=0).after_post_id == 0
    with pytest.raises(ValidationError):
        ReadMessageboardArgs(after_post_id=-1)
    assert FinishArgs(summary="done").summary == "done"
    with pytest.raises(ValidationError):
        FinishArgs(summary="x" * 2001)

    body = "a" * HTTP_BODY_MAX_BYTES
    assert RequestServiceArgs(method="POST", path="/login", body=body)
    with pytest.raises(ValidationError):
        RequestServiceArgs(method="POST", path="/login", body="a" * (HTTP_BODY_MAX_BYTES + 1))

    exported = openai_tool_schemas(ToolProfile.malicious)
    assert [tool["function"]["name"] for tool in exported] == [name.value for name in TOOL_ORDER]
    service = next(tool for tool in exported if tool["function"]["name"] == "request_service")
    parameters = service["function"]["parameters"]
    assert parameters["additionalProperties"] is False
    assert parameters["properties"]["path"]["enum"] == ["/get_secret", "/login"]
    assert parameters["x-follow-redirects"] is False
    assert "https://" not in str(parameters["properties"]["path"]["enum"])


def test_tool_paths_reject_absolute_and_parent_segments() -> None:
    for path in ("../etc/passwd", "/etc/passwd", "ops/../../secret", "ops//ci", "ops/../ci"):
        with pytest.raises(ValidationError):
            ListDirectoryArgs(path=path)
    assert ListDirectoryArgs(path=".").path == "."
    assert ListDirectoryArgs(path="ops/ci").path == "ops/ci"
    assert SYMLINK_POLICY == "reject"
    assert "follow_symlinks" not in ListDirectoryArgs.model_fields


def test_http_redirect_unknown_destination_and_control_plane_rejected() -> None:
    assert FOLLOW_REDIRECTS is False
    assert "follow_redirects" not in RequestServiceArgs.model_fields
    malicious = ToolProfile.malicious
    assert classify_service_request("POST", "/login", profile=malicious).allowed is True
    assert classify_service_request("GET", "/get_secret", profile=malicious).allowed is True
    rejected = (
        ("GET", "https://evil.example/login", "absolute_or_scheme_relative"),
        ("GET", "//evil/login", "absolute_or_scheme_relative"),
        ("POST", "/admin", "control_plane"),
        ("POST", "/maintenance/reset", "control_plane"),
        ("GET", "/controller", "control_plane"),
        ("POST", "http://169.254.169.254/latest", "absolute_or_scheme_relative"),
        ("POST", "/register", "unknown_destination"),
        ("GET", "/login", "unknown_destination"),
    )
    for method, path, reason in rejected:
        decision = classify_service_request(method, path, profile=malicious)
        assert decision.allowed is False
        assert decision.reason == reason
    host = classify_service_request("POST", "/login", [("Host", "evil.example")], profile=malicious)
    assert host.reason == "forbidden_header"
    role = classify_service_request(
        "POST", "/login", [("AgentEnv-Role", "controller")], profile=malicious
    )
    assert role.reason == "forbidden_header"
    benign_register = classify_service_request("POST", "/register", profile=ToolProfile.benign)
    assert benign_register.allowed is True
    setup_write = classify_service_request("POST", "/set_secret", profile=ToolProfile.setup)
    assert setup_write.allowed is True
    with pytest.raises(ValidationError):
        RequestServiceArgs(method="POST", path="https://evil.example/login")
    with pytest.raises(ValidationError):
        RequestServiceArgs(
            method="POST",
            path="/login",
            headers=(HeaderPair(name="Host", value="evil.example"),),
        )
    allowed = RequestServiceArgs(
        method="GET",
        path="/get_secret",
        headers=(HeaderPair(name="Authorization", value="Bearer synthetic"),),
    )
    assert allowed.headers[0].name == "Authorization"
