"""Event envelope and role projections."""

from adaptivehoneypotenv.contracts.actions import PLACEHOLDER_DESCRIPTION_IDS
from adaptivehoneypotenv.contracts.events import (
    ActorHistoryView,
    ActorTurnRejected,
    DecoyExposed,
    DefenderEventView,
    EpisodeStarted,
    MessageboardPosted,
    MessageboardRead,
    OperatorEventView,
    Principal,
    ToolCompleted,
    TurnRejectionReason,
    compute_derived_id,
    project_actor_history,
    project_defender,
    project_operator,
    validate_journal,
)
from adaptivehoneypotenv.contracts.telemetry import PathCategory
from adaptivehoneypotenv.contracts.tools import AttackerToolName
from tests.support import EPISODE_ID, envelope


def _tool(
    sequence: int,
    tool_name: AttackerToolName,
    *,
    actor_id: str = "attacker-1",
) -> ToolCompleted:
    return ToolCompleted(
        kind="tool_completed",
        tool_name=tool_name,
        normalized_path="ops/deploy" if tool_name is AttackerToolName.list_directory else None,
        path_category=PathCategory.ops_deploy
        if tool_name is AttackerToolName.list_directory
        else PathCategory.none,
        **envelope(
            "tool_completed",
            sequence,
            actor=Principal(role="attacker", actor_id=actor_id),
            attempt_index=sequence,
        ),
    )


def test_messageboard_activity_absent_from_defender_telemetry() -> None:
    posted = MessageboardPosted(
        kind="messageboard_posted",
        post_id=1,
        author_actor_id="attacker-1",
        char_count=12,
        **envelope("messageboard_posted", 0),
    )
    read = MessageboardRead(
        kind="messageboard_read",
        after_post_id=0,
        returned_count=1,
        clipped=False,
        **envelope("messageboard_read", 1, attempt_index=1),
    )
    board_tool = _tool(2, AttackerToolName.post_to_messageboard)
    visible = _tool(3, AttackerToolName.list_directory)

    assert project_defender(posted) is None
    assert project_defender(read) is None
    assert project_defender(board_tool) is None
    projected = project_defender(visible)
    assert projected is not None
    assert projected.tool_name is not None
    assert projected.tool_name.value == "list_directory"
    dumped = projected.model_dump_json()
    assert "messageboard" not in dumped
    forbidden = {"post_id", "char_count", "after_post_id", "text", "posts", "messageboard"}
    assert forbidden.isdisjoint(DefenderEventView.model_fields)

    operator_view = project_operator(posted)
    assert operator_view.post_id == 1
    assert operator_view.char_count == 12
    assert "text" not in OperatorEventView.model_fields
    assert "text" not in MessageboardPosted.model_fields


def test_messageboard_posts_are_never_pushed_into_histories() -> None:
    posted = MessageboardPosted(
        kind="messageboard_posted",
        post_id=4,
        author_actor_id="attacker-1",
        char_count=8,
        **envelope("messageboard_posted", 0),
    )
    read = MessageboardRead(
        kind="messageboard_read",
        after_post_id=0,
        returned_count=0,
        clipped=False,
        **envelope("messageboard_read", 1, actor=Principal(role="attacker", actor_id="attacker-2")),
    )
    own_tool = _tool(2, AttackerToolName.read_messageboard, actor_id="attacker-1")

    assert project_actor_history(posted, actor_id="attacker-1") is None
    assert project_actor_history(posted, actor_id="attacker-2") is None
    assert project_actor_history(read, actor_id="attacker-2") is None
    own_history = project_actor_history(own_tool, actor_id="attacker-1")
    assert own_history is not None
    assert own_history.tool_name is AttackerToolName.read_messageboard
    assert "text" not in ActorHistoryView.model_fields
    assert "posts" not in ActorHistoryView.model_fields
    assert project_actor_history(own_tool, actor_id="attacker-2") is None


def test_derived_event_id_ignores_wall_clock_and_cites_sources() -> None:
    sources = (0, 1)
    kind = "decoy_exposed"
    derived = compute_derived_id(EPISODE_ID, kind, sources)
    first = DecoyExposed(
        kind="decoy_exposed",
        source_sequences=sources,
        deterministic_id=derived,
        recipient_actor_id="attacker-1",
        decoy_public_id="decoy_abc12345",
        **envelope(
            kind,
            2,
            actor=Principal(role="system", actor_id="scorer"),
            wall_time_unix_ns=10,
        ),
    )
    second = DecoyExposed(
        kind="decoy_exposed",
        source_sequences=sources,
        deterministic_id=derived,
        recipient_actor_id="attacker-1",
        decoy_public_id="decoy_abc12345",
        **envelope(
            kind,
            2,
            actor=Principal(role="system", actor_id="scorer"),
            wall_time_unix_ns=99,
        ),
    )
    assert first.deterministic_id == second.deterministic_id
    assert first.event_id == second.event_id
    assert "protected_value" not in DecoyExposed.model_fields
    view = project_defender(first)
    assert view is not None
    assert view.decoy_public_id == "decoy_abc12345"
    assert view.source_sequences == sources

    started = EpisodeStarted(
        kind="episode_started",
        scenario_id="secret_store_ops/v1",
        catalogue_ordering_version="secret_store_ops/v1.ordering.1",
        team="trio",
        **envelope("episode_started", 0, actor=Principal(role="controller", actor_id="controller")),
    )
    rejected = ActorTurnRejected(
        kind="actor_turn_rejected",
        reason_category=TurnRejectionReason.multiple_tool_calls,
        **envelope("actor_turn_rejected", 1),
    )
    validate_journal([started, rejected])
    assert PLACEHOLDER_DESCRIPTION_IDS
