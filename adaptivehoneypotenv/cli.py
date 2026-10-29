"""Episode commands for the trusted controller.

``gate-a`` and ``gate-b`` run real Docker episodes with the scripted defender
and no attacker model. ``run --defender live`` is the only path that constructs
the OpenRouter adapter, and it refuses to do so until the operator supplies
the token and cost caps. This module does not read provider credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from adaptivehoneypotenv.contracts.actions import (
    SLOT_DIRECTORIES,
    CatalogueDecoySpec,
    ContextId,
    ContextualDecoySpec,
    SlotId,
    TemplateId,
)
from adaptivehoneypotenv.contracts.events import (
    DeploymentCommitted,
    DeploymentRejected,
    ModelCallFinished,
    ModelCallStarted,
    validate_journal,
)
from adaptivehoneypotenv.contracts.limits import (
    MAX_DECOYS,
    TEAM_ATTEMPT_BUDGET,
    TEAM_GENERATED_TOKEN_BUDGET,
)
from adaptivehoneypotenv.deployment import Deployment, EpisodeTarget
from adaptivehoneypotenv.env import EpisodeCore
from adaptivehoneypotenv.gateway.messageboard import MessageboardError
from adaptivehoneypotenv.model_api import (
    ChatCompletionResult,
    ChatMessage,
    FinishReason,
    TokenUsage,
    ToolCall,
)
from adaptivehoneypotenv.policies import ScriptedDefender
from adaptivehoneypotenv.scenario import approved_description_ids
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.solver import (
    SecretStorageClientError,
    export_solver_trace,
    solve_reference_route,
)
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.spec import ACCOUNT_ROLES
from adaptivehoneypotenv.server import OperatorServer

_REPO = Path(__file__).resolve().parents[1]
_RUNS = _REPO / "runs"
_PROBE = _REPO / "scripts" / "containment_probe.py"
_SEED = 17
_MAINTENANCE = "Maintenance note added during the March review of on-file accounts."
_SCORING = frozenset(
    {
        "decoy_exposed",
        "decoy_inspected",
        "decoy_authenticated",
        "verified_engagement",
        "protected_value_exposed",
    }
)
_PAIRS: tuple[tuple[tuple[str, str, str], tuple[str, str, str]], ...] = (
    (
        ("integration_config", "deployment_notes", "release"),
        ("ci_credential_record", "ci_records", "backup"),
    ),
    (
        ("integration_config", "deployment_notes", "backup"),
        ("ci_credential_record", "ci_records", "release"),
    ),
    (
        ("integration_config", "integration_records", "release"),
        ("runbook_reference", "runbooks", "backup"),
    ),
    (
        ("integration_config", "integration_records", "backup"),
        ("runbook_reference", "runbooks", "release"),
    ),
    (
        ("ci_credential_record", "deployment_notes", "release"),
        ("runbook_reference", "runbooks", "release"),
    ),
    (
        ("ci_credential_record", "deployment_notes", "backup"),
        ("runbook_reference", "runbooks", "backup"),
    ),
)


class _GateFailure(Exception):
    def __init__(self, token: str) -> None:
        super().__init__(token)
        self.token = token


class _SetupRoute:
    """Setup-route client for the reference solver. Not an attacker tool."""

    def __init__(self, core: EpisodeCore) -> None:
        self._client = core.deployment().setup_client(core.target())

    def login(self, email: str, password: str) -> str:
        response = self._client.login(email, password)
        token = _json_field(response, "token")
        if response.status_code != 200 or not isinstance(token, str) or not token:
            raise SecretStorageClientError("login_failed")
        return token

    def get_secret(self, token: str, username: str) -> str:
        response = self._client.get_secret(username, token)
        secret = _json_field(response, "secret")
        if response.status_code != 200 or not isinstance(secret, str):
            raise SecretStorageClientError("get_failed")
        return secret


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="adaptivehoneypotenv")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("gate-a")
    sub.add_parser("gate-b")
    observe = sub.add_parser("observe")
    observe.add_argument("--messageboard", choices=("memory", "swarmchat"), default="memory")
    run = sub.add_parser(
        "run",
        help="run a full live episode or a single defender-only scripted smoke transition",
        description=(
            "Live mode runs defender/attacker transitions until the episode ends. "
            "Scripted mode checks one defender transition without attacker models."
        ),
    )
    run.add_argument("--defender", choices=("scripted", "live"), required=True)
    run.add_argument("--attacker-max-tokens", type=int)
    run.add_argument("--defender-max-tokens", type=int)
    run.add_argument("--max-cost-usd")
    run.add_argument("--seed", type=int, default=_SEED)
    run.add_argument("--messageboard", choices=("memory", "swarmchat"), default="memory")
    args = parser.parse_args(argv)
    try:
        if args.command == "gate-a":
            return _gate_a()
        if args.command == "gate-b":
            return _gate_b()
        if args.command == "observe":
            return _observe(args.messageboard)
        if args.defender == "live":
            return _run_live(args)
        return _run_scripted(args.seed, args.messageboard)
    except MessageboardError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except _GateFailure as exc:
        print(exc.token, file=sys.stderr)
        return 1


def _gate_a() -> int:
    root = _RUNS / "gate-a"
    core = EpisodeCore(root, team="trio", track="catalogue", repo_root=_REPO)
    try:
        _reset(core)
        result = core.step_defender(_defender(_wait_result()), core.mint_action_id())
        _require(result.info.valid, "transition_invalid")
        _require(result.reward == Decimal("0"), "reward")
        _require(not result.terminated and not result.truncated, "ended")
        _require(core.user_count() == len(ACCOUNT_ROLES) == 9, "user_count")
        _require(core.app_pid() == core.baseline_pid, "pid")
        _require(core.deployment().secret_is_strong(core.target()), "app_secret")
        _require(_solver_matches(core), "solver_match")
        _require(_containment(core.deployment(), core.target()), "containment")
        _require(_journal_clean(core, scripted=True), "journal")
        observation = core.observation()
        _require(observation.remaining_team_attempts == TEAM_ATTEMPT_BUDGET, "attempts")
        _require(
            observation.remaining_team_generated_tokens == TEAM_GENERATED_TOKEN_BUDGET,
            "tokens",
        )
        _require(observation.remaining_decoy_budget == MAX_DECOYS, "decoy_budget")
        _require(bool(observation.safe_action_mask) and observation.safe_action_mask[0], "mask")
        _require(core.defender_request_is_redacted(), "redaction")
        _write_summary(
            root / "summary.json",
            {"gate": "gate-a", "episode_id": core.episode_id, "ok": True},
        )
    finally:
        core.close()
    print("true", flush=True)
    return 0


def _gate_b() -> int:
    _reject_long_description()
    root = _RUNS / "gate-b"
    deployment = Deployment(_REPO)
    descriptions = approved_description_ids()
    cursor = 0
    try:
        for index, pair in enumerate(_PAIRS):
            specs, cursor = _catalogue_pair(pair, descriptions, cursor)
            extra = None
            if index == 0:
                third, cursor = _one_catalogue(
                    ("integration_config", "integration_records", "release"),
                    descriptions,
                    cursor,
                )
                extra = third
            _pair_episode(deployment, root, specs, extra)
        occupied, cursor = _one_catalogue(
            ("ci_credential_record", "ci_records", "backup"),
            descriptions,
            cursor,
        )
        mixed, cursor = _catalogue_pair(
            (
                ("integration_config", "deployment_notes", "release"),
                ("ci_credential_record", "ci_records", "backup"),
            ),
            descriptions,
            cursor,
        )
        _invalid_batch_episode(deployment, root, occupied, mixed)
        rollback, cursor = _catalogue_pair(
            (
                ("integration_config", "deployment_notes", "release"),
                ("ci_credential_record", "ci_records", "backup"),
            ),
            descriptions,
            cursor,
        )
        _rollback_episode(deployment, root, rollback)
        _contextual_episode(deployment, root)
    finally:
        deployment.close()
    _write_summary(root / "summary.json", {"gate": "gate-b", "ok": True})
    print("true", flush=True)
    return 0


def _observe(messageboard: Literal["memory", "swarmchat"] = "memory") -> int:
    root = _RUNS / "observe"
    core = EpisodeCore(
        root, team="trio", track="catalogue", repo_root=_REPO, messageboard_backend=messageboard
    )
    server: OperatorServer | None = None
    try:
        _reset(core)
        core.step_defender(_defender(_wait_result()), core.mint_action_id())
        _require(core.defender_request_is_redacted(), "redaction")
        server = OperatorServer(core)
        print(f"http://127.0.0.1:{server.port}/events", flush=True)
        print("http://127.0.0.1:5173/?mode=live&screen=run", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    finally:
        if server is not None:
            server.close()
        core.close()
    return 0


def _run_scripted(seed: int, messageboard: Literal["memory", "swarmchat"] = "memory") -> int:
    root = _RUNS / "scripted"
    core = EpisodeCore(
        root, team="trio", track="catalogue", repo_root=_REPO, messageboard_backend=messageboard
    )
    try:
        _reset(core, seed)
        result = core.step_defender(_defender(_wait_result()), core.mint_action_id())
        _require(result.info.valid, "transition_invalid")
        _require(core.defender_request_is_redacted(), "redaction")
    finally:
        core.close()
    print("true", flush=True)
    return 0


def _run_live(args: argparse.Namespace) -> int:
    attacker_max = args.attacker_max_tokens
    defender_max = args.defender_max_tokens
    cost = args.max_cost_usd
    if attacker_max is None or defender_max is None or not cost:
        print("missing live caps; no model call was made", file=sys.stderr)
        return 2
    try:
        amount = Decimal(cost)
    except Exception:
        print("invalid cost; no model call was made", file=sys.stderr)
        return 2
    try:
        from adaptivehoneypotenv.models.adapter import OpenAICompatibleAdapter
        from adaptivehoneypotenv.models.config import AdapterConfig
    except Exception:
        print("live adapter import failed; no model call was made", file=sys.stderr)
        return 2
    ledger = _RUNS / "live" / "private" / "spend.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(ledger.parent, 0o700)
    try:
        config = AdapterConfig(
            cap_usd=amount,
            ledger_path=ledger,
            attacker_max_tokens=attacker_max,
            attacker_per_call_cap=attacker_max,
            defender_max_tokens=defender_max,
            defender_per_call_cap=defender_max,
        )
    except Exception:
        print("invalid caps; no model call was made", file=sys.stderr)
        return 2
    attacker = OpenAICompatibleAdapter(config)
    defender = OpenAICompatibleAdapter(config)
    core = EpisodeCore(
        _RUNS / "live",
        team="trio",
        track="catalogue",
        repo_root=_REPO,
        attacker_adapter=attacker,
        attacker_per_call_cap=attacker_max,
        defender_max_tokens=defender_max,
        messageboard_backend=args.messageboard,
    )
    try:
        _reset(core, args.seed)
        transitions = 0
        while True:
            result = core.step_defender(defender, core.mint_action_id())
            transitions += 1
            if not result.info.valid or result.terminated or result.truncated:
                break
        print(
            json.dumps(
                {
                    "episode_id": core.episode_id,
                    "defender_transitions": transitions,
                    "valid": result.info.valid,
                    "terminated": result.terminated,
                    "truncated": result.truncated,
                    "termination_reason": result.info.termination_reason,
                    "truncation_reason": result.info.truncation_reason,
                    "invalid_reason": result.info.invalid_reason,
                }
            ),
            flush=True,
        )
        return 0 if result.info.valid else 1
    except KeyboardInterrupt:
        core.kill()
        print("operator_kill", file=sys.stderr, flush=True)
        return 130
    finally:
        core.close()


def _pair_episode(
    deployment: Deployment,
    root: Path,
    specs: list[dict[str, Any]],
    extra: dict[str, Any] | None,
) -> None:
    script = [_deploy_result(specs)]
    if extra is not None:
        script.append(_deploy_result([extra]))
    core = _episode(deployment, root)
    try:
        action_id = core.mint_action_id()
        defender = _defender(*script)
        result = core.step_defender(defender, action_id)
        users = core.user_count()
        _require(result.info.valid, "pair_invalid")
        _require(core.user_count() == core.baseline_user_count + 2, "pair_users")
        _require(core.app_pid() == core.baseline_pid, "pair_pid")
        _require(core.world_version == 1, "pair_version")
        _require(core.observation().remaining_decoy_budget == 0, "pair_budget")
        mask = core.observation().safe_action_mask
        _require(mask[0] and not any(mask[1:]), "pair_mask")
        _require(_both_routes(core), "pair_routes")
        _require(core.decoy_files_within_budget(), "pair_files")
        _require(_decoys_ok(core), "pair_decoys")
        _require(_one_commit(core, 2), "pair_commit")
        _require(_journal_clean(core, scripted=True), "pair_journal")
        _require(core.replay_ok(), "pair_replay")
        if extra is not None:
            again = core.step_defender(defender, action_id)
            _require(core.user_count() == users, "idempotent_users")
            _require(again.info.valid, "idempotent_valid")
            third = core.step_defender(defender, core.mint_action_id())
            _require(third.info.valid, "budget_valid")
            _require(core.user_count() == users, "budget_users")
            _require(_rejected(core, "budget"), "budget_reject")
            _require(_one_commit(core, 2), "budget_commit")
    finally:
        core.close()


def _invalid_batch_episode(
    deployment: Deployment,
    root: Path,
    occupied: dict[str, Any],
    mixed: list[dict[str, Any]],
) -> None:
    core = _episode(deployment, root)
    try:
        defender = _defender(_deploy_result([occupied]), _deploy_result(mixed))
        first = core.step_defender(defender, core.mint_action_id())
        _require(first.info.valid, "single_invalid")
        _require(core.user_count() == core.baseline_user_count + 1, "single_users")
        slot = SLOT_DIRECTORIES[SlotId.deployment_notes]
        before = _files(core.active_workspace(), slot)
        second = core.step_defender(defender, core.mint_action_id())
        _require(second.info.valid, "batch_invalid")
        _require(core.user_count() == core.baseline_user_count + 1, "batch_users")
        _require(_files(core.active_workspace(), slot) == before, "free_slot_changed")
        _require(_one_commit(core, 1), "batch_commit")
        _require(
            any(event.kind == "deployment_rejected" for event in core.events()), "batch_reject"
        )
        _require(_journal_clean(core, scripted=True), "batch_journal")
    finally:
        core.close()


def _rollback_episode(
    deployment: Deployment,
    root: Path,
    specs: list[dict[str, Any]],
) -> None:
    core = EpisodeCore(
        root,
        deployment=deployment,
        team="trio",
        track="catalogue",
        repo_root=_REPO,
        fault_stage="after_first_account",
    )
    try:
        _reset(core)
        result = core.step_defender(_defender(_deploy_result(specs)), core.mint_action_id())
        _require(result.info.valid, "rollback_invalid")
        _require(core.user_count() == core.baseline_user_count, "rollback_users")
        _require(core.app_pid() == core.baseline_pid, "rollback_pid")
        _require(core.world_version == 0, "rollback_version")
        _require(core.active_workspace().name == "0000", "rollback_workspace")
        _require(core.attempted_accounts_absent(), "rollback_login")
        _require(
            not any(isinstance(event, DeploymentCommitted) for event in core.events()),
            "rollback_commit",
        )
        _require(_journal_clean(core, scripted=True), "rollback_journal")
    finally:
        core.close()


def _contextual_episode(deployment: Deployment, root: Path) -> None:
    spec = ContextualDecoySpec(
        track="contextual",
        template_id=TemplateId.integration_config,
        slot_id=SlotId.deployment_notes,
        context_id=ContextId.release,
        description=_MAINTENANCE,
    )
    core = EpisodeCore(
        root,
        deployment=deployment,
        team="trio",
        track="contextual",
        repo_root=_REPO,
    )
    try:
        _reset(core)
        result = core.step_defender(
            _defender(_deploy_result([spec.model_dump(mode="json")])),
            core.mint_action_id(),
        )
        _require(result.info.valid, "contextual_invalid")
        owned = core.observation().owned_deployments
        _require(len(owned) == 1, "contextual_count")
        _require(owned[0].track == "contextual", "contextual_track")
        _require(owned[0].description == _MAINTENANCE, "contextual_text")
        _require(owned[0].description_id is None, "contextual_id")
        _require(core.contextual_description_present(), "contextual_file")
        _require(core.decoy_files_within_budget(), "contextual_files")
        _require(_decoys_ok(core), "contextual_decoy")
        _require(_both_routes(core), "contextual_routes")
        _require(core.user_count() == core.baseline_user_count + 1, "contextual_users")
        _require(core.app_pid() == core.baseline_pid, "contextual_pid")
        _require(_journal_clean(core, scripted=True), "contextual_journal")
        _require(core.replay_ok(), "contextual_replay")
    finally:
        core.close()


def _episode(deployment: Deployment, root: Path) -> EpisodeCore:
    core = EpisodeCore(
        root,
        deployment=deployment,
        team="trio",
        track="catalogue",
        repo_root=_REPO,
    )
    _reset(core)
    return core


def _reset(core: EpisodeCore, seed: int = _SEED) -> None:
    try:
        core.reset(seed)
    except RuntimeError:
        raise _GateFailure("reset_failed") from None
    journal = core.journal_directory()
    print(f"{core.episode_id} {journal}", flush=True)
    board_dir = core.messageboard_directory()
    if board_dir is not None:
        print(f"SwarmChat data (private): {board_dir}", flush=True)
        print(
            "Open with: uv run --extra swarmchat swarmchat view --data <that-directory>", flush=True
        )


def _solver_matches(core: EpisodeCore) -> bool:
    route = _SetupRoute(core)
    workspace = core.active_workspace()
    private = _private_dir(core)
    matched = True
    for workflow in ("release", "backup"):
        try:
            trace = solve_reference_route(workspace, workflow, route)
        except (SecretStorageClientError, Exception):
            return False
        stored = trace.stored_value or ""
        matched = matched and core.matches_stored_value(workflow, stored)
        dest = private / f"solver-{workflow}.json"
        export_solver_trace(trace, dest)
        os.chmod(dest, 0o600)
        if dest.stat().st_mode & 0o777 != 0o600:
            return False
    return matched


def _containment(deployment: Deployment, episode: EpisodeTarget) -> bool:
    facts = deployment.containment_facts(episode)
    if facts.get("network_internal") is not True:
        return False
    for role in ("target", "bridge"):
        item = facts[role]
        if item["port_bindings"] not in (None, {}):
            return False
        mounted = " ".join([*item["mount_sources"], *item["binds"]])
        if "sock" in mounted:
            return False
    gateway = deployment.gateway_ipv4(episode)
    bridge_ip = deployment.container_ipv4(episode, "bridge")
    target_report = _run_probe(
        deployment,
        episode,
        {
            "tcp": [
                ["1.1.1.1", 443],
                ["1.1.1.1", 80],
                ["8.8.8.8", 53],
                [gateway, 2375],
                [gateway, 80],
            ],
            "dns": ["8.8.8.8"],
            "names": ["example.com"],
            "bridge": {"ip": bridge_ip, "port": 8080},
        },
        "target",
    )
    bridge_report = _run_probe(
        deployment,
        episode,
        {
            "tcp": [["1.1.1.1", 443], ["8.8.8.8", 53]],
            "dns": ["8.8.8.8"],
            "names": ["example.com"],
        },
        "bridge",
    )
    for report in (target_report, bridge_report):
        for detail in report["tcp"].values():
            if not _blocked(detail):
                return False
        for detail in report["dns"].values():
            if not _blocked(detail):
                return False
        for detail in report["names"].values():
            if not _blocked(detail):
                return False
    bridge_request = target_report["bridge_request"]
    absolute = bridge_request.get("absolute", "")
    connect = bridge_request.get("connect", "")
    return "unknown_destination" in absolute and "unknown_destination" in connect


def _run_probe(
    deployment: Deployment,
    episode: EpisodeTarget,
    config: dict[str, Any],
    container: str,
) -> dict[str, Any]:
    script = _PROBE.read_text(encoding="utf-8")
    completed = deployment.admin_exec(
        episode,
        ["python3", "-c", script, json.dumps(config)],
        container=container,
    )
    if completed.exit_code != 0:
        raise _GateFailure("probe_exec")
    loaded = json.loads(completed.stdout.decode())
    if not isinstance(loaded, dict):
        raise _GateFailure("probe_exec")
    return loaded


def _journal_clean(core: EpisodeCore, *, scripted: bool) -> bool:
    events = core.events()
    try:
        validate_journal(events)
    except ValueError:
        return False
    journal = core.journal_directory()
    if journal is None or not (journal / "events.jsonl").is_file():
        return False
    if not events or events[0].kind != "episode_started":
        return False
    if any(event.kind in _SCORING for event in events):
        return False
    model_events = [
        event for event in events if isinstance(event, (ModelCallStarted, ModelCallFinished))
    ]
    if scripted and not model_events:
        return False
    for event in model_events:
        if event.actor.role != "defender":
            return False
        if scripted and event.adapter_id != "scripted_test_double":
            return False
    return True


def _both_routes(core: EpisodeCore) -> bool:
    return core.workflow_route_ok("release") and core.workflow_route_ok("backup")


def _decoys_ok(core: EpisodeCore) -> bool:
    identities = core.decoy_public_ids()
    return bool(identities) and all(core.decoy_status(item) == "ok" for item in identities)


def _one_commit(core: EpisodeCore, count: int) -> bool:
    commits = [event for event in core.events() if isinstance(event, DeploymentCommitted)]
    return len(commits) == 1 and len(commits[0].deployment_ids) == count


def _rejected(core: EpisodeCore, reason: str) -> bool:
    return any(
        isinstance(event, DeploymentRejected) and event.reason_category.value == reason
        for event in core.events()
    )


def _files(root: Path, relative: str) -> set[str]:
    base = root / relative
    if not base.exists():
        return set()
    return {
        path.relative_to(root).as_posix()
        for path in base.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def _private_dir(core: EpisodeCore) -> Path:
    journal = core.journal_directory()
    if journal is None:
        raise _GateFailure("journal")
    private = journal.parent / "private"
    private.mkdir(parents=True, exist_ok=True)
    return private


def _reject_long_description() -> None:
    try:
        ContextualDecoySpec(
            track="contextual",
            template_id=TemplateId.integration_config,
            slot_id=SlotId.deployment_notes,
            context_id=ContextId.release,
            description="a" * 241,
        )
    except ValidationError:
        return
    raise _GateFailure("description_limit")


def _catalogue_pair(
    pair: tuple[tuple[str, str, str], tuple[str, str, str]],
    descriptions: tuple[str, ...],
    cursor: int,
) -> tuple[list[dict[str, Any]], int]:
    first, cursor = _one_catalogue(pair[0], descriptions, cursor)
    second, cursor = _one_catalogue(pair[1], descriptions, cursor)
    return [first, second], cursor


def _one_catalogue(
    item: tuple[str, str, str],
    descriptions: tuple[str, ...],
    cursor: int,
) -> tuple[dict[str, Any], int]:
    template, slot, context = item
    spec = CatalogueDecoySpec(
        track="catalogue",
        template_id=TemplateId(template),
        slot_id=SlotId(slot),
        context_id=ContextId(context),
        description_id=descriptions[cursor % len(descriptions)],
    )
    return spec.model_dump(mode="json"), cursor + 1


def _defender(*results: ChatCompletionResult) -> ScriptedDefender:
    return ScriptedDefender(results)


def _wait_result() -> ChatCompletionResult:
    return _completion("wait", "{}", "call_wait")


def _deploy_result(specs: list[dict[str, Any]]) -> ChatCompletionResult:
    return _completion("deploy", json.dumps({"decoys": specs}), "call_deploy")


def _completion(name: str, arguments: str, call_id: str) -> ChatCompletionResult:
    return ChatCompletionResult(
        message=ChatMessage(
            role="assistant",
            tool_calls=(ToolCall(id=call_id, name=name, arguments_json=arguments),),
        ),
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
        finish_reason=FinishReason.tool_calls,
    )


def _blocked(detail: object) -> bool:
    if not isinstance(detail, str):
        return False
    lowered = detail.lower()
    if lowered == "open" or lowered.startswith(("response:", "answers")):
        return False
    if "refused" in lowered:
        return False
    return True


def _json_field(response: object, field: str) -> object:
    reader = getattr(response, "json", None)
    if not callable(reader):
        return None
    try:
        body = reader()
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    return body.get(field)


def _require(condition: bool, token: str) -> None:
    if not condition:
        raise _GateFailure(token)


def _write_summary(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
