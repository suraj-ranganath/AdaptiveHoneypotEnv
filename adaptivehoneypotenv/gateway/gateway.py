"""Trusted execution of the seven attacker tools.

The controller calls ``execute`` or ``apply_turn`` once per counted attempt.
Results are journaled before they are returned. Messageboard text stays in
the private payload store and in the calling actor's delivery. Defender
projections and defender activity omit board contents, counts, and timing.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from adaptivehoneypotenv.contracts.events import (
    ActorHistoryView,
    ActorTurnRejected,
    DefenderEventView,
    Event,
    EventStatus,
    MessageboardPosted,
    MessageboardRead,
    OperatorEventView,
    PayloadRef,
    Principal,
    ToolCompleted,
    ToolStarted,
    TurnRejectionReason,
    compute_event_id,
    project_actor_history,
    project_defender,
    project_operator,
)
from adaptivehoneypotenv.contracts.limits import HTTP_RESPONSE_MAX_BYTES
from adaptivehoneypotenv.contracts.observations import RedactedActivity, project_search_term
from adaptivehoneypotenv.contracts.telemetry import (
    HttpMethodCategory,
    HttpStatusCategory,
    PathCategory,
    category_for_workspace_path,
)
from adaptivehoneypotenv.contracts.tools import (
    FOLLOW_REDIRECTS,
    TOOL_MODELS,
    AttackerToolName,
    FinishArgs,
    ListDirectoryArgs,
    PostToMessageboardArgs,
    ReadFileArgs,
    ReadMessageboardArgs,
    RequestServiceArgs,
    SearchFilesArgs,
    ToolProfile,
    classify_service_request,
    validate_workspace_path,
)
from adaptivehoneypotenv.gateway.budget import AttemptLedger, TokenCharge, TokenLedger
from adaptivehoneypotenv.gateway.filesystem import (
    DirectoryListing,
    FileSlice,
    FilesystemFailure,
    FilesystemRefusal,
    SearchFindings,
    list_directory,
    read_file,
    search_files,
)
from adaptivehoneypotenv.gateway.journal import EpisodeJournal, JournalWriteError
from adaptivehoneypotenv.gateway.messageboard import BoardPage, Messageboard, PostedMessage
from adaptivehoneypotenv.gateway.upstream import FixedUpstream, UpstreamExchangeError
from adaptivehoneypotenv.model_api import TokenUsage, ToolCall

_ACTOR_ID = re.compile(r"^attacker-[123]$")
_EPISODE_ID = re.compile(r"^ep_[A-Za-z0-9_-]{8,64}$")
_FEEDBACK = {
    TurnRejectionReason.zero_tool_calls: "one tool call is required",
    TurnRejectionReason.multiple_tool_calls: "exactly one tool call is allowed",
    TurnRejectionReason.malformed_arguments: "tool arguments were rejected",
    TurnRejectionReason.plain_text: "plain text does not run a tool",
    TurnRejectionReason.provider_refusal: "provider refusal ended this session",
}


class GatewayError(Exception):
    """Controller-facing failure. The reason is a stable token."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ToolDelivery(BaseModel):
    """Bytes returned to the actor that invoked the turn. Do not broadcast."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    status: EventStatus
    consumed_attempt: bool
    clipped: bool
    content: str
    content_sha256: str
    reason: str | None = None
    tool_name: str | None = None
    episode_valid: bool = True


@dataclass
class _Result:
    content: dict[str, Any]
    status: EventStatus
    clipped: bool = False
    reason: str | None = None
    normalized_path: str | None = None
    path_category: PathCategory = PathCategory.none
    sanitized_search_term: str = ""
    search_clipped: bool = False
    returned_hit_count: int = 0
    http_method: HttpMethodCategory = HttpMethodCategory.none
    http_status_category: HttpStatusCategory = HttpStatusCategory.none
    raw: bytes | None = None
    commit_post: PostedMessage | None = None
    board_post: PostedMessage | None = None
    board_page: BoardPage | None = None
    after_post_id: int | None = None
    finish_actor: bool = False
    uncertain: bool = False


class ToolGateway:
    """Per-episode gateway. One instance serves every attacker on the team."""

    def __init__(
        self,
        *,
        episode_id: str,
        workspace: Path,
        upstream: FixedUpstream,
        controller_token: str,
        profile: ToolProfile = ToolProfile.malicious,
        team: str = "trio",
        fixture_literals: tuple[str, ...] = (),
        journal_dir: Path | None = None,
        world_version: int = 0,
    ) -> None:
        if FOLLOW_REDIRECTS:
            raise GatewayError("redirects_forbidden")
        if not _EPISODE_ID.fullmatch(episode_id):
            raise GatewayError("episode_id")
        if team not in {"solo", "trio"}:
            raise GatewayError("team")
        if controller_token == "":
            raise GatewayError("controller_token")
        if world_version < 0:
            raise GatewayError("world_version")
        root = workspace
        if root.is_symlink() or not root.is_dir():
            raise GatewayError("workspace")
        directory = None if journal_dir is None else Path(journal_dir)
        self._episode_id = episode_id
        self._root = root
        self._upstream = upstream
        self._controller_token = controller_token
        self._profile = profile
        self._fixture_literals = fixture_literals
        self._world_version = world_version
        self._journal = EpisodeJournal(episode_id, directory)
        self._board = Messageboard(solo=team == "solo")
        self._attempts = AttemptLedger()
        self._tokens = TokenLedger()
        self._finished: set[str] = set()
        self._episode_valid = True
        self._invalid_reason: str | None = None
        self._lock = threading.RLock()

    @property
    def episode_valid(self) -> bool:
        return self._episode_valid

    @property
    def invalid_reason(self) -> str | None:
        return self._invalid_reason

    @property
    def attempts_used(self) -> int:
        return self._attempts.used

    @property
    def remaining_attempts(self) -> int:
        return self._attempts.remaining

    @property
    def attempt_budget(self) -> int:
        return self._attempts.budget

    @property
    def generated_tokens_used(self) -> int:
        return self._tokens.used

    @property
    def remaining_generated_tokens(self) -> int:
        return self._tokens.remaining

    @property
    def generated_token_budget(self) -> int:
        return self._tokens.budget

    @property
    def token_accounting_available(self) -> bool:
        return self._tokens.available

    @property
    def events(self) -> tuple[Event, ...]:
        with self._lock:
            return self._journal.events

    @property
    def message_count(self) -> int:
        """Controller-side length. Not part of any defender projection."""

        with self._lock:
            return len(self._board)

    def set_world_version(self, world_version: int) -> None:
        with self._lock:
            if world_version < self._world_version:
                raise GatewayError("world version decreased")
            self._world_version = world_version

    def account_generated_tokens(
        self,
        usage: TokenUsage,
        *,
        request_id: str,
        reported_generated: int | None = None,
    ) -> TokenCharge:
        """Charge reconciled generated tokens. Prompt tokens are not charged."""

        with self._lock:
            self._require_valid()
            return self._tokens.account(
                usage,
                request_id=request_id,
                reported_generated=reported_generated,
            )

    def generated_token_cap(self, *, per_call_cap: int, parallel_calls: int) -> int:
        with self._lock:
            return self._tokens.per_call_cap(
                per_call_cap=per_call_cap,
                parallel_calls=parallel_calls,
            )

    def payload(self, ref_id: str) -> bytes:
        with self._lock:
            return self._journal.payload(ref_id)

    def iter_payloads(self) -> tuple[bytes, ...]:
        with self._lock:
            return self._journal.iter_payloads()

    def defender_views(self) -> tuple[DefenderEventView, ...]:
        with self._lock:
            views: list[DefenderEventView] = []
            for event in self._journal.events:
                view = project_defender(event)
                if view is not None:
                    views.append(view)
            return tuple(views)

    def defender_activity(self) -> tuple[RedactedActivity, ...]:
        """Visible tool completions only. Messageboard attempts are omitted."""

        with self._lock:
            items: list[RedactedActivity] = []
            for event in self._journal.events:
                if not isinstance(event, ToolCompleted):
                    continue
                if project_defender(event) is None:
                    continue
                items.append(_activity_from(event))
            return tuple(items)

    def actor_history(self, actor_id: str) -> tuple[ActorHistoryView, ...]:
        with self._lock:
            views: list[ActorHistoryView] = []
            for event in self._journal.events:
                view = project_actor_history(event, actor_id=actor_id)
                if view is not None:
                    views.append(view)
            return tuple(views)

    def operator_views(self) -> tuple[OperatorEventView, ...]:
        with self._lock:
            return tuple(project_operator(event) for event in self._journal.events)

    def execute(
        self,
        *,
        actor_id: str,
        round_index: int,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> ToolDelivery:
        with self._lock:
            return self._execute(
                actor_id=actor_id,
                round_index=round_index,
                tool_name=tool_name,
                arguments=arguments,
            )

    def apply_turn(
        self,
        *,
        actor_id: str,
        round_index: int,
        tool_calls: Sequence[ToolCall] = (),
        plain_text: str | None = None,
        refusal: str | None = None,
    ) -> ToolDelivery:
        """Count one model turn. Zero or many tool calls execute nothing."""

        with self._lock:
            if refusal is not None:
                return self._reject_turn(
                    actor_id=actor_id,
                    round_index=round_index,
                    reason=TurnRejectionReason.provider_refusal,
                    status=EventStatus.refused,
                    finish=True,
                )
            if len(tool_calls) > 1:
                return self._reject_turn(
                    actor_id=actor_id,
                    round_index=round_index,
                    reason=TurnRejectionReason.multiple_tool_calls,
                    status=EventStatus.invalid,
                    finish=False,
                )
            if len(tool_calls) == 0:
                reason = (
                    TurnRejectionReason.plain_text
                    if plain_text
                    else TurnRejectionReason.zero_tool_calls
                )
                return self._reject_turn(
                    actor_id=actor_id,
                    round_index=round_index,
                    reason=reason,
                    status=EventStatus.invalid,
                    finish=False,
                )
            call = tool_calls[0]
            try:
                parsed = json.loads(call.arguments_json)
            except json.JSONDecodeError:
                return self._reject_turn(
                    actor_id=actor_id,
                    round_index=round_index,
                    reason=TurnRejectionReason.malformed_arguments,
                    status=EventStatus.invalid,
                    finish=False,
                )
            if not isinstance(parsed, dict):
                return self._reject_turn(
                    actor_id=actor_id,
                    round_index=round_index,
                    reason=TurnRejectionReason.malformed_arguments,
                    status=EventStatus.invalid,
                    finish=False,
                )
            return self._execute(
                actor_id=actor_id,
                round_index=round_index,
                tool_name=call.name,
                arguments=parsed,
            )

    def _execute(
        self,
        *,
        actor_id: str,
        round_index: int,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> ToolDelivery:
        blocked = self._precheck(actor_id, round_index)
        if blocked is not None:
            return blocked
        try:
            tool = AttackerToolName(tool_name)
        except ValueError:
            return self._reject_turn(
                actor_id=actor_id,
                round_index=round_index,
                reason=TurnRejectionReason.malformed_arguments,
                status=EventStatus.invalid,
                finish=False,
            )
        policy = _policy_reason(tool, arguments, self._profile)
        attempt = self._consume_or_exhausted(actor_id)
        if isinstance(attempt, ToolDelivery):
            return attempt
        if policy is not None:
            return self._rejected_tool(
                actor_id=actor_id,
                round_index=round_index,
                attempt=attempt,
                tool=tool,
                reason=policy,
                method=_service_method(arguments)
                if tool is AttackerToolName.request_service
                else None,
            )
        try:
            parsed = TOOL_MODELS[tool].model_validate(dict(arguments))
        except ValidationError:
            return self._rejected_consumed(
                actor_id=actor_id,
                round_index=round_index,
                attempt=attempt,
                reason=TurnRejectionReason.malformed_arguments,
                status=EventStatus.invalid,
                finish=False,
            )
        try:
            return self._run_parsed(
                actor_id=actor_id,
                round_index=round_index,
                attempt=attempt,
                tool=tool,
                parsed=parsed,
            )
        except JournalWriteError as exc:
            self._invalidate("journal_write_failed")
            raise GatewayError("journal_write_failed") from exc

    def _run_parsed(
        self,
        *,
        actor_id: str,
        round_index: int,
        attempt: int,
        tool: AttackerToolName,
        parsed: BaseModel,
    ) -> ToolDelivery:
        started = time.perf_counter_ns()
        path, category = _started_path(tool, parsed)
        self._append(
            self._tool_started(
                attempt=attempt,
                round_index=round_index,
                actor_id=actor_id,
                tool=tool,
                normalized_path=path,
                path_category=category,
            )
        )
        result = self._dispatch(
            actor_id=actor_id,
            round_index=round_index,
            tool=tool,
            parsed=parsed,
        )
        result_path = result.normalized_path if result.normalized_path is not None else path
        result_category = (
            result.path_category if result.path_category is not PathCategory.none else category
        )
        if tool is AttackerToolName.request_service:
            result_category = PathCategory.service
            result_path = None
        duration = time.perf_counter_ns() - started
        body = canonical(result.content)
        refs = [self._journal.store(body)]
        if result.raw is not None:
            refs.append(self._journal.store(result.raw))
        if result.uncertain:
            self._invalidate("uncertain_outcome")
        self._append(
            self._tool_completed(
                attempt=attempt,
                round_index=round_index,
                actor_id=actor_id,
                tool=tool,
                status=result.status,
                duration_ns=duration,
                refs=tuple(refs),
                normalized_path=result_path,
                path_category=result_category,
                result=result,
            )
        )
        self._append_board_event(
            result=result,
            attempt=attempt,
            round_index=round_index,
            actor_id=actor_id,
            duration_ns=duration,
            refs=tuple(refs),
        )
        if result.commit_post is not None:
            self._board.commit(result.commit_post)
        if result.finish_actor:
            self._finished.add(actor_id)
        return _delivery(
            status=result.status,
            consumed=True,
            clipped=result.clipped,
            body=body,
            reason=result.reason,
            tool_name=tool.value,
            episode_valid=self._episode_valid,
        )

    def _dispatch(
        self,
        *,
        actor_id: str,
        round_index: int,
        tool: AttackerToolName,
        parsed: BaseModel,
    ) -> _Result:
        if tool is AttackerToolName.list_directory and isinstance(parsed, ListDirectoryArgs):
            return _from_filesystem(
                parsed.path,
                lambda: list_directory(self._root, parsed.path),
                _listing,
            )
        if tool is AttackerToolName.search_files and isinstance(parsed, SearchFilesArgs):
            return self._search(parsed)
        if tool is AttackerToolName.read_file and isinstance(parsed, ReadFileArgs):
            return _from_filesystem(
                parsed.path,
                lambda: read_file(self._root, parsed.path, parsed.start_line, parsed.max_lines),
                _file_slice,
            )
        if tool is AttackerToolName.request_service and isinstance(parsed, RequestServiceArgs):
            return self._service(actor_id, parsed)
        if tool is AttackerToolName.post_to_messageboard and isinstance(
            parsed, PostToMessageboardArgs
        ):
            return self._post(actor_id, round_index, parsed)
        if tool is AttackerToolName.read_messageboard and isinstance(parsed, ReadMessageboardArgs):
            return self._read_board(actor_id, round_index, parsed)
        if tool is AttackerToolName.finish and isinstance(parsed, FinishArgs):
            return _Result(
                content={"finished": True},
                status=EventStatus.ok,
                raw=parsed.summary.encode("utf-8"),
                finish_actor=True,
            )
        raise GatewayError("unhandled_tool")

    def _search(self, parsed: SearchFilesArgs) -> _Result:
        sanitized = project_search_term(parsed.query, fixture_literals=self._fixture_literals)

        def run() -> SearchFindings:
            return search_files(self._root, parsed.path, parsed.query)

        def pack(findings: SearchFindings) -> _Result:
            return _Result(
                content={
                    "clipped": findings.clipped,
                    "hits": [
                        {"line": hit.line, "path": hit.path, "text": hit.text}
                        for hit in findings.hits
                    ],
                },
                status=EventStatus.clipped if findings.clipped else EventStatus.ok,
                clipped=findings.clipped,
                normalized_path=parsed.path,
                path_category=category_for_workspace_path(parsed.path),
                sanitized_search_term=sanitized,
                search_clipped=findings.clipped,
                returned_hit_count=len(findings.hits),
            )

        try:
            return pack(run())
        except FilesystemRefusal as exc:
            return _Result(
                content={"rejected": exc.reason},
                status=EventStatus.rejected,
                reason=exc.reason,
                normalized_path=None if exc.reason == "traversal" else parsed.path,
                path_category=category_for_workspace_path(parsed.path),
                sanitized_search_term=sanitized,
            )
        except FilesystemFailure as exc:
            return _Result(
                content={"error": exc.reason},
                status=EventStatus.error,
                reason=exc.reason,
                normalized_path=parsed.path,
                path_category=category_for_workspace_path(parsed.path),
                sanitized_search_term=sanitized,
            )

    def _service(self, actor_id: str, parsed: RequestServiceArgs) -> _Result:
        method = HttpMethodCategory(parsed.method)
        decision = classify_service_request(
            parsed.method,
            parsed.path,
            [(header.name, header.value) for header in parsed.headers],
            profile=self._profile,
            query=parsed.query,
        )
        if not decision.allowed:
            return _service_rejection(decision.reason or "unknown_destination", method)
        try:
            response = self._upstream.exchange(
                method=parsed.method,
                path=_service_target(parsed.path, parsed.query),
                headers=tuple((header.name, header.value) for header in parsed.headers),
                body=parsed.body.encode("utf-8"),
                actor_id=actor_id,
                controller_token=self._controller_token,
            )
        except UpstreamExchangeError as exc:
            return _Result(
                content={"error": "uncertain_outcome" if exc.uncertain else "transport_error"},
                status=EventStatus.error,
                reason=exc.reason,
                http_method=method,
                http_status_category=HttpStatusCategory.other,
                uncertain=exc.uncertain,
            )
        if 300 <= response.status_code < 400:
            return _Result(
                content={"rejected": "redirect"},
                status=EventStatus.rejected,
                reason="redirect",
                http_method=method,
                http_status_category=HttpStatusCategory.other,
                raw=response.body,
            )
        clipped_body, clipped = _clip_http_body(response.body)
        if response.body_truncated:
            clipped = True
        try:
            text = clipped_body.decode("utf-8")
        except UnicodeDecodeError:
            return _Result(
                content={"error": "not_utf8"},
                status=EventStatus.error,
                reason="not_utf8",
                http_method=method,
                http_status_category=_status_category(response.status_code),
                raw=response.body,
            )
        return _Result(
            content={"body": text, "clipped": clipped, "status_code": response.status_code},
            status=EventStatus.clipped if clipped else EventStatus.ok,
            clipped=clipped,
            http_method=method,
            http_status_category=_status_category(response.status_code),
            raw=response.body,
        )

    def _post(self, actor_id: str, round_index: int, parsed: PostToMessageboardArgs) -> _Result:
        post = self._board.prepare(
            author_actor_id=actor_id,
            round_index=round_index,
            text=parsed.text,
        )
        return _Result(
            content={
                "char_count": post.char_count,
                "post_id": post.post_id,
                "round_index": round_index,
            },
            status=EventStatus.ok,
            commit_post=post,
            board_post=post,
            raw=parsed.text.encode("utf-8"),
        )

    def _read_board(self, actor_id: str, round_index: int, parsed: ReadMessageboardArgs) -> _Result:
        page = self._board.read(
            reader_actor_id=actor_id,
            round_index=round_index,
            after_post_id=parsed.after_post_id,
        )
        return _Result(
            content={
                "clipped": page.clipped,
                "posts": [_post_view(post) for post in page.posts],
            },
            status=EventStatus.clipped if page.clipped else EventStatus.ok,
            clipped=page.clipped,
            board_page=page,
            after_post_id=parsed.after_post_id,
        )

    def _reject_turn(
        self,
        *,
        actor_id: str,
        round_index: int,
        reason: TurnRejectionReason,
        status: EventStatus,
        finish: bool,
    ) -> ToolDelivery:
        blocked = self._precheck(actor_id, round_index)
        if blocked is not None:
            return blocked
        attempt = self._consume_or_exhausted(actor_id)
        if isinstance(attempt, ToolDelivery):
            return attempt
        try:
            return self._rejected_consumed(
                actor_id=actor_id,
                round_index=round_index,
                attempt=attempt,
                reason=reason,
                status=status,
                finish=finish,
            )
        except JournalWriteError as exc:
            self._invalidate("journal_write_failed")
            raise GatewayError("journal_write_failed") from exc

    def _rejected_consumed(
        self,
        *,
        actor_id: str,
        round_index: int,
        attempt: int,
        reason: TurnRejectionReason,
        status: EventStatus,
        finish: bool,
    ) -> ToolDelivery:
        feedback = _FEEDBACK[reason]
        body = canonical({"feedback": feedback, "reason": reason.value})
        ref = self._journal.store(body)
        self._append(
            ActorTurnRejected(
                kind="actor_turn_rejected",
                reason_category=reason,
                payload_refs=(ref,),
                **self._envelope(
                    kind="actor_turn_rejected",
                    status=status,
                    attempt=attempt,
                    round_index=round_index,
                    actor_id=actor_id,
                    duration_ns=0,
                ),
            )
        )
        if finish:
            self._finished.add(actor_id)
        return _delivery(
            status=status,
            consumed=True,
            clipped=False,
            body=body,
            reason=reason.value,
            tool_name=None,
            episode_valid=self._episode_valid,
        )

    def _rejected_tool(
        self,
        *,
        actor_id: str,
        round_index: int,
        attempt: int,
        tool: AttackerToolName,
        reason: str,
        method: str | None,
    ) -> ToolDelivery:
        try:
            self._append(
                self._tool_started(
                    attempt=attempt,
                    round_index=round_index,
                    actor_id=actor_id,
                    tool=tool,
                    normalized_path=None,
                    path_category=PathCategory.service
                    if tool is AttackerToolName.request_service
                    else PathCategory.none,
                )
            )
            content: dict[str, Any] = {"rejected": reason}
            body = canonical(content)
            ref = self._journal.store(body)
            http_method = HttpMethodCategory.none
            http_status = HttpStatusCategory.none
            if tool is AttackerToolName.request_service and method in {"GET", "POST"}:
                http_method = HttpMethodCategory(method)
                http_status = HttpStatusCategory.other
            result = _Result(
                content=content,
                status=EventStatus.rejected,
                reason=reason,
                http_method=http_method,
                http_status_category=http_status,
            )
            self._append(
                self._tool_completed(
                    attempt=attempt,
                    round_index=round_index,
                    actor_id=actor_id,
                    tool=tool,
                    status=EventStatus.rejected,
                    duration_ns=0,
                    refs=(ref,),
                    normalized_path=None,
                    path_category=PathCategory.service
                    if tool is AttackerToolName.request_service
                    else PathCategory.none,
                    result=result,
                )
            )
            return _delivery(
                status=EventStatus.rejected,
                consumed=True,
                clipped=False,
                body=body,
                reason=reason,
                tool_name=tool.value,
                episode_valid=self._episode_valid,
            )
        except JournalWriteError as exc:
            self._invalidate("journal_write_failed")
            raise GatewayError("journal_write_failed") from exc

    def _append_board_event(
        self,
        *,
        result: _Result,
        attempt: int,
        round_index: int,
        actor_id: str,
        duration_ns: int,
        refs: tuple[PayloadRef, ...],
    ) -> None:
        if result.board_post is not None:
            post = result.board_post
            self._append(
                MessageboardPosted(
                    kind="messageboard_posted",
                    post_id=post.post_id,
                    author_actor_id=post.author_actor_id,
                    char_count=post.char_count,
                    payload_refs=refs,
                    **self._envelope(
                        kind="messageboard_posted",
                        status=EventStatus.ok,
                        attempt=attempt,
                        round_index=round_index,
                        actor_id=actor_id,
                        duration_ns=duration_ns,
                    ),
                )
            )
        if result.board_page is not None and result.after_post_id is not None:
            self._append(
                MessageboardRead(
                    kind="messageboard_read",
                    after_post_id=result.after_post_id,
                    returned_count=len(result.board_page.posts),
                    clipped=result.board_page.clipped,
                    payload_refs=refs,
                    **self._envelope(
                        kind="messageboard_read",
                        status=EventStatus.clipped if result.board_page.clipped else EventStatus.ok,
                        attempt=attempt,
                        round_index=round_index,
                        actor_id=actor_id,
                        duration_ns=duration_ns,
                    ),
                )
            )

    def _tool_started(
        self,
        *,
        attempt: int,
        round_index: int,
        actor_id: str,
        tool: AttackerToolName,
        normalized_path: str | None,
        path_category: PathCategory,
    ) -> ToolStarted:
        return ToolStarted(
            kind="tool_started",
            tool_name=tool,
            normalized_path=normalized_path,
            path_category=path_category,
            **self._envelope(
                kind="tool_started",
                status=EventStatus.ok,
                attempt=attempt,
                round_index=round_index,
                actor_id=actor_id,
                duration_ns=0,
            ),
        )

    def _tool_completed(
        self,
        *,
        attempt: int,
        round_index: int,
        actor_id: str,
        tool: AttackerToolName,
        status: EventStatus,
        duration_ns: int,
        refs: tuple[PayloadRef, ...],
        normalized_path: str | None,
        path_category: PathCategory,
        result: _Result,
    ) -> ToolCompleted:
        return ToolCompleted(
            kind="tool_completed",
            tool_name=tool,
            normalized_path=normalized_path,
            path_category=path_category,
            sanitized_search_term=result.sanitized_search_term,
            search_clipped=result.search_clipped,
            returned_hit_count=result.returned_hit_count,
            http_method=result.http_method,
            http_status_category=result.http_status_category,
            clipped=result.clipped,
            payload_refs=refs,
            **self._envelope(
                kind="tool_completed",
                status=status,
                attempt=attempt,
                round_index=round_index,
                actor_id=actor_id,
                duration_ns=duration_ns,
            ),
        )

    def _envelope(
        self,
        *,
        kind: str,
        status: EventStatus,
        attempt: int,
        round_index: int,
        actor_id: str,
        duration_ns: int,
    ) -> dict[str, Any]:
        sequence = self._journal.next_sequence()
        return {
            "event_id": compute_event_id(self._episode_id, sequence, kind),
            "episode_id": self._episode_id,
            "sequence": sequence,
            "round_index": round_index,
            "attempt_index": attempt,
            "world_version": self._world_version,
            "actor": Principal(role="attacker", actor_id=actor_id),
            "status": status,
            "monotonic_duration_ns": duration_ns,
            "wall_time_unix_ns": time.time_ns(),
            "request_id": f"req-{sequence}",
        }

    def _append(self, event: Event) -> None:
        self._journal.append(event)

    def _precheck(self, actor_id: str, round_index: int) -> ToolDelivery | None:
        self._require_valid()
        if _ACTOR_ID.fullmatch(actor_id) is None:
            raise GatewayError("actor_id")
        if round_index < 0:
            raise GatewayError("round_index")
        events = self._journal.events
        if events and round_index < events[-1].round_index:
            raise GatewayError("round index decreased")
        if actor_id in self._finished:
            body = canonical({"rejected": "actor_finished"})
            return _delivery(
                status=EventStatus.rejected,
                consumed=False,
                clipped=False,
                body=body,
                reason="actor_finished",
                tool_name=None,
                episode_valid=True,
            )
        return None

    def _consume_or_exhausted(self, actor_id: str) -> int | ToolDelivery:
        attempt = self._attempts.try_consume()
        if attempt is None:
            body = canonical({"rejected": "attempt_exhaustion"})
            return _delivery(
                status=EventStatus.rejected,
                consumed=False,
                clipped=False,
                body=body,
                reason="attempt_exhaustion",
                tool_name=None,
                episode_valid=self._episode_valid,
            )
        return attempt

    def _require_valid(self) -> None:
        if not self._episode_valid:
            raise GatewayError(self._invalid_reason or "episode_invalid")

    def _invalidate(self, reason: str) -> None:
        self._episode_valid = False
        self._invalid_reason = reason


def _policy_reason(
    tool: AttackerToolName,
    arguments: Mapping[str, Any],
    profile: ToolProfile,
) -> str | None:
    if tool in {
        AttackerToolName.list_directory,
        AttackerToolName.search_files,
        AttackerToolName.read_file,
    }:
        path = arguments.get("path")
        if not isinstance(path, str):
            return None
        try:
            validate_workspace_path(path)
        except ValueError as exc:
            text = str(exc)
            if "traversal" in text or "absolute" in text:
                return "traversal"
            return "invalid_path"
        return None
    if tool is not AttackerToolName.request_service:
        return None
    method = arguments.get("method")
    path = arguments.get("path")
    if method not in {"GET", "POST"} or not isinstance(path, str):
        return None
    headers = _header_pairs(arguments.get("headers", []))
    if headers is None:
        return None
    query = arguments.get("query", "")
    if not isinstance(query, str):
        return None
    decision = classify_service_request(method, path, headers, profile=profile, query=query)
    if decision.allowed:
        return None
    return decision.reason


def _header_pairs(raw: object) -> list[tuple[str, str]] | None:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return None
    pairs: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            return None
        pairs.append((name, value))
    return pairs


def _service_method(arguments: Mapping[str, Any]) -> str | None:
    method = arguments.get("method")
    if method in {"GET", "POST"}:
        return str(method)
    return None


def _service_target(path: str, query: str) -> str:
    """Request target. A non-empty query is the caller's text, not a new key."""

    if query == "":
        return path
    return f"{path}?{query}"


def _service_rejection(reason: str, method: HttpMethodCategory) -> _Result:
    return _Result(
        content={"rejected": reason},
        status=EventStatus.rejected,
        reason=reason,
        http_method=method,
        http_status_category=HttpStatusCategory.other,
    )


def _started_path(tool: AttackerToolName, parsed: BaseModel) -> tuple[str | None, PathCategory]:
    path: str | None = None
    if isinstance(parsed, (ListDirectoryArgs, SearchFilesArgs, ReadFileArgs)):
        path = parsed.path
    if tool is AttackerToolName.request_service:
        return None, PathCategory.service
    if path is None:
        return None, PathCategory.none
    return path, category_for_workspace_path(path)


def _from_filesystem(
    path: str,
    run: Any,
    pack: Any,
) -> _Result:
    category = category_for_workspace_path(path)
    try:
        value = run()
    except FilesystemRefusal as exc:
        return _Result(
            content={"rejected": exc.reason},
            status=EventStatus.rejected,
            reason=exc.reason,
            normalized_path=None if exc.reason == "traversal" else path,
            path_category=category,
        )
    except FilesystemFailure as exc:
        return _Result(
            content={"error": exc.reason},
            status=EventStatus.error,
            reason=exc.reason,
            normalized_path=path,
            path_category=category,
        )
    result: _Result = pack(value)
    result.normalized_path = path
    result.path_category = category
    return result


def _listing(listing: DirectoryListing) -> _Result:
    return _Result(
        content={
            "clipped": listing.clipped,
            "entries": [{"kind": entry.kind, "name": entry.name} for entry in listing.entries],
        },
        status=EventStatus.clipped if listing.clipped else EventStatus.ok,
        clipped=listing.clipped,
    )


def _file_slice(file_slice: FileSlice) -> _Result:
    return _Result(
        content={
            "clipped": file_slice.clipped,
            "lines": [{"number": number, "text": text} for number, text in file_slice.lines],
        },
        status=EventStatus.clipped if file_slice.clipped else EventStatus.ok,
        clipped=file_slice.clipped,
    )


def _post_view(post: PostedMessage) -> dict[str, Any]:
    return {
        "author": post.author_actor_id,
        "post_id": post.post_id,
        "round_index": post.round_index,
        "text": post.text,
    }


def _clip_http_body(body: bytes) -> tuple[bytes, bool]:
    if len(body) <= HTTP_RESPONSE_MAX_BYTES:
        return body, False
    clipped = body[:HTTP_RESPONSE_MAX_BYTES]
    while clipped:
        try:
            clipped.decode("utf-8")
            return clipped, True
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return b"", True


def _status_category(code: int) -> HttpStatusCategory:
    if 200 <= code <= 299:
        return HttpStatusCategory.success
    if 400 <= code <= 499:
        return HttpStatusCategory.client_error
    if 500 <= code <= 599:
        return HttpStatusCategory.server_error
    return HttpStatusCategory.other


def _activity_from(event: ToolCompleted) -> RedactedActivity:
    return RedactedActivity(
        tool_name=event.tool_name,  # type: ignore[arg-type]
        normalized_path=event.normalized_path,
        path_category=event.path_category,
        sanitized_search_term=event.sanitized_search_term,
        search_clipped=event.search_clipped,
        returned_hit_count=event.returned_hit_count,
        http_method=event.http_method,
        http_status_category=event.http_status_category,
        actor_id=event.actor.actor_id,
        attempt_number=event.attempt_index,
        sequence_number=event.sequence,
        duration_ns=event.monotonic_duration_ns,
    )


def canonical(payload: Mapping[str, Any]) -> bytes:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return encoded.encode("utf-8")


def _delivery(
    *,
    status: EventStatus,
    consumed: bool,
    clipped: bool,
    body: bytes,
    reason: str | None,
    tool_name: str | None,
    episode_valid: bool,
) -> ToolDelivery:
    return ToolDelivery(
        status=status,
        consumed_attempt=consumed,
        clipped=clipped,
        content=body.decode("utf-8"),
        content_sha256=hashlib.sha256(body).hexdigest(),
        reason=reason,
        tool_name=tool_name,
        episode_valid=episode_valid,
    )
