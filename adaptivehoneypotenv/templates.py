"""Deterministic decoy compiler.

The model selects a template, slot, context, and bounded description.
Credential and canary bytes come from ``secrets.SystemRandom``. Deploy
mutates the running service through backup and restore. It does not restart
the process. A failed transaction restores the snapshot taken at its start.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from adaptivehoneypotenv.contracts.actions import CatalogueDecoySpec, ContextualDecoySpec
from adaptivehoneypotenv.deployment import (
    Deployment,
    DeploymentError,
    EpisodeTarget,
    MaintenanceError,
    ServiceClient,
)
from adaptivehoneypotenv.gateway.gateway import ToolGateway
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.fixtures import FixtureBundle
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.templates.renderers import render_decoy

DecoySpec = CatalogueDecoySpec | ContextualDecoySpec
FaultStage = str | None
_FAULTS = frozenset({"after_render", "after_first_account", "after_accounts", "before_publish"})


class CompilerFault(Exception):
    """Injected fault. The transaction rolls back and the episode stays valid."""


class CompilerError(Exception):
    """A compiler failure. ``reason`` is a token and contains no secret bytes."""

    def __init__(self, reason: str, *, recoverable: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.recoverable = recoverable


@dataclass(frozen=True)
class StagedAccount:
    public_id: str
    deployment_id: str
    spec: DecoySpec
    username: str
    email: str
    password: str
    canary: str
    paths: tuple[str, ...]
    digests: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class StageResult:
    ok: bool
    recovered: bool
    invalidate: bool
    reason: str | None
    accounts: tuple[StagedAccount, ...]
    attempted_usernames: tuple[str, ...]
    staging_dir: Path | None


class DecoyCompiler:
    """One compiler bound to the episode target and the private run directory."""

    def __init__(
        self,
        deployment: Deployment,
        target: EpisodeTarget,
        gateway: ToolGateway,
        bundle: FixtureBundle,
        private_dir: Path,
        versions_dir: Path,
        *,
        fault_stage: FaultStage = None,
    ) -> None:
        if fault_stage is not None and fault_stage not in _FAULTS:
            raise ValueError("unknown compiler fault stage")
        self._deployment = deployment
        self._target = target
        self._gateway = gateway
        self._bundle = bundle
        self._private = private_dir
        self._versions = versions_dir
        self._fault = fault_stage
        self._next_version = 1
        self._client: ServiceClient | None = None
        self._pending_texts: dict[str, dict[str, str]] = {}
        self._last_logins: tuple[tuple[str, str], ...] = ()

    @property
    def last_logins(self) -> tuple[tuple[str, str], ...]:
        """Email and password of accounts this transaction tried to create."""

        return self._last_logins

    def stage(self, specs: tuple[DecoySpec, ...], transaction_id: str) -> StageResult:
        attempted: list[str] = []
        logins: list[tuple[str, str]] = []
        staging: Path | None = None
        backed_up = False
        users_before = 0
        pid_before = 0
        try:
            users_before = self._deployment.user_count(self._target)
            pid_before = self._deployment.app_pid(self._target)
            staged = self._render(specs)
            self._intent(transaction_id, specs)
            self._maybe("after_render")
            self._deployment.backup(self._target)
            backed_up = True
            staging = self._materialize(staged)
            self._create_accounts(staged, attempted, logins)
            self._verify_genuine()
            self._maybe("before_publish")
            return StageResult(
                ok=True,
                recovered=False,
                invalidate=False,
                reason=None,
                accounts=tuple(staged),
                attempted_usernames=tuple(attempted),
                staging_dir=staging,
            )
        except CompilerFault:
            return self._rollback(
                backed_up=backed_up,
                mutated=bool(attempted),
                staging=staging,
                attempted=attempted,
                users_before=users_before,
                pid_before=pid_before,
                reason="fault_injected",
            )
        except CompilerError as exc:
            if exc.recoverable and backed_up:
                return self._rollback(
                    backed_up=True,
                    mutated=bool(attempted),
                    staging=staging,
                    attempted=attempted,
                    users_before=users_before,
                    pid_before=pid_before,
                    reason=exc.reason,
                )
            self._discard(staging)
            return StageResult(
                ok=False,
                recovered=False,
                invalidate=True,
                reason=exc.reason,
                accounts=(),
                attempted_usernames=tuple(attempted),
                staging_dir=None,
            )
        except (MaintenanceError, DeploymentError):
            self._discard(staging)
            return StageResult(
                ok=False,
                recovered=False,
                invalidate=True,
                reason="maintenance_failed",
                accounts=(),
                attempted_usernames=tuple(attempted),
                staging_dir=None,
            )
        except Exception:
            if backed_up and attempted:
                try:
                    self._deployment.restore(self._target)
                except (MaintenanceError, DeploymentError):
                    pass
            self._discard(staging)
            return StageResult(
                ok=False,
                recovered=False,
                invalidate=True,
                reason="compiler_error",
                accounts=(),
                attempted_usernames=tuple(attempted),
                staging_dir=None,
            )
        finally:
            self._last_logins = tuple(logins)

    def publish(self, staging: Path, world_version: int) -> None:
        self._gateway.set_world_version(world_version)
        _write_private(self._private / "active_workspace.txt", (staging.name + "\n").encode())
        self._gateway.set_workspace(staging)
        self._next_version += 1

    def _render(self, specs: tuple[DecoySpec, ...]) -> list[StagedAccount]:
        rng = secrets.SystemRandom()
        bundle = self._bundle
        occupied = _files(self._gateway.workspace)
        genuine_secrets = {account.stored_value for account in bundle.accounts.values()}
        genuine_passwords = {account.password for account in bundle.accounts.values()}
        staged: list[StagedAccount] = []
        pending: dict[str, dict[str, str]] = {}
        for spec in specs:
            rendered = None
            for _ in range(8):
                candidate = render_decoy(bundle, spec, rng, occupied_paths=occupied)
                secret = candidate.account.stored_value
                password = candidate.account.password
                if secret in genuine_secrets or password in genuine_passwords:
                    continue
                if secret == self._bundle.stored_value_for_workflow(self._bundle.workflow):
                    continue
                rendered = candidate
                break
            if rendered is None:
                raise CompilerError("collision", recoverable=False)
            total = sum(len(item.text.encode("utf-8")) for item in rendered.files)
            if len(rendered.files) > 2 or total > 4096:
                raise CompilerError("render_budget", recoverable=False)
            public_id = "decoy_" + secrets.token_hex(8)
            deployment_id = "dep_" + secrets.token_hex(8)
            paths = tuple(item.relative_path for item in rendered.files)
            digests = tuple(
                (item.relative_path, hashlib.sha256(item.text.encode("utf-8")).hexdigest())
                for item in rendered.files
            )
            staged.append(
                StagedAccount(
                    public_id=public_id,
                    deployment_id=deployment_id,
                    spec=spec,
                    username=rendered.account.username,
                    email=rendered.account.email,
                    password=rendered.account.password,
                    canary=rendered.account.stored_value,
                    paths=paths,
                    digests=digests,
                )
            )
            pending[public_id] = {item.relative_path: item.text for item in rendered.files}
            occupied.update(paths)
            bundle = replace(
                bundle,
                accounts={
                    **bundle.accounts,
                    public_id: rendered.account,
                },
            )
        self._pending_texts = pending
        return staged

    def _materialize(self, staged: list[StagedAccount]) -> Path:
        active = self._gateway.workspace
        _assert_no_symlinks(active)
        staging = self._versions / f"{self._next_version:04d}"
        if staging.exists():
            raise CompilerError("version_exists", recoverable=False)
        shutil.copytree(active, staging, symlinks=False)
        for account in staged:
            texts = self._pending_texts[account.public_id]
            for relative, text in texts.items():
                target = staging / relative
                if target.exists():
                    raise CompilerError("path_occupied", recoverable=True)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8", newline="\n")
        return staging

    def _create_accounts(
        self,
        staged: list[StagedAccount],
        attempted: list[str],
        logins: list[tuple[str, str]],
    ) -> None:
        client = self._setup()
        for index, account in enumerate(staged):
            registered = client.register(account.email, account.username, account.password)
            if registered.status_code != 201:
                raise CompilerError("register_failed", recoverable=True)
            attempted.append(account.username)
            logins.append((account.email, account.password))
            if self._fault == "after_first_account" and index == 0:
                raise CompilerFault()
            logged = client.login(account.email, account.password)
            token = _token(logged)
            if token is None:
                raise CompilerError("login_failed", recoverable=True)
            stored = client.set_secret(account.username, account.canary, token)
            if stored.status_code != 200:
                raise CompilerError("set_failed", recoverable=True)
            readback = client.get_secret(account.username, token)
            if readback.status_code != 200 or _secret(readback) != account.canary:
                raise CompilerError("canary_mismatch", recoverable=True)
        if self._fault == "after_accounts":
            raise CompilerFault()

    def _verify_genuine(self) -> None:
        client = self._setup()
        for workflow in ("release", "backup"):
            account = self._bundle.account_for_workflow(workflow)
            logged = client.login(account.email, account.password)
            token = _token(logged)
            if token is None:
                raise CompilerError("genuine_login_failed", recoverable=True)
            readback = client.get_secret(account.username, token)
            if readback.status_code != 200 or _secret(readback) != account.stored_value:
                raise CompilerError("genuine_mismatch", recoverable=True)

    def _rollback(
        self,
        *,
        backed_up: bool,
        mutated: bool,
        staging: Path | None,
        attempted: list[str],
        users_before: int,
        pid_before: int,
        reason: str,
    ) -> StageResult:
        invalidate = False
        if backed_up and mutated:
            try:
                self._deployment.restore(self._target)
            except (MaintenanceError, DeploymentError):
                invalidate = True
            else:
                try:
                    pid_now = self._deployment.app_pid(self._target)
                    users_now = self._deployment.user_count(self._target)
                except (MaintenanceError, DeploymentError):
                    invalidate = True
                else:
                    if pid_now != pid_before or users_now != users_before:
                        invalidate = True
        self._discard(staging)
        return StageResult(
            ok=False,
            recovered=not invalidate,
            invalidate=invalidate,
            reason=reason,
            accounts=(),
            attempted_usernames=tuple(attempted),
            staging_dir=None,
        )

    def _maybe(self, stage: str) -> None:
        if self._fault == stage:
            raise CompilerFault()

    def _setup(self) -> ServiceClient:
        if self._client is None:
            self._client = self._deployment.setup_client(self._target)
        return self._client

    def _intent(self, transaction_id: str, specs: tuple[DecoySpec, ...]) -> None:
        lines = [
            "{",
            f'  "transaction_id": "{transaction_id}",',
            f'  "spec_count": {len(specs)}',
            "}",
            "",
        ]
        _write_private(self._private / f"intent-{transaction_id}.json", "\n".join(lines).encode())

    def _discard(self, staging: Path | None) -> None:
        if staging is not None and staging.is_dir():
            shutil.rmtree(staging, ignore_errors=True)


def _files(root: Path) -> set[str]:
    found: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise CompilerError("symlink", recoverable=False)
        if path.is_file():
            found.add(path.relative_to(root).as_posix())
    return found


def _assert_no_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise CompilerError("symlink", recoverable=False)


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _token(response: object) -> str | None:
    status = getattr(response, "status_code", None)
    reader = getattr(response, "json", None)
    if status != 200 or not callable(reader):
        return None
    try:
        body = reader()
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    token = body.get("token")
    if not isinstance(token, str) or token == "":
        return None
    return token


def _secret(response: object) -> str | None:
    reader = getattr(response, "json", None)
    if not callable(reader):
        return None
    try:
        body = reader()
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    secret = body.get("secret")
    if not isinstance(secret, str):
        return None
    return secret
