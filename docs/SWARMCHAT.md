# SwarmChat integration

SwarmChat is an optional backend for **attacker communication inside an episode**. It stores real board posts and supplies its native Chat, Board, and Map viewer. AgentEnv remains the environment integration, and the episode core remains responsible for scheduling, scoring, budgets, and replay.

The dependency is SwarmChat `0.1.0`, locked to [commit fb5aa6a](https://github.com/Pranjal2041/swarmchat/tree/fb5aa6a05b40fba70f749cd3017aeb3219ab6ac1). It runs locally in the trusted controller. No account on swarmchat.io or external messaging service is used.

## Enable it

```bash
uv sync --frozen --all-groups --extra swarmchat
```

Select the backend when constructing the existing core:

```python
core = EpisodeCore(run_root, messageboard_backend="swarmchat")
```

Pass the same attacker adapter and other settings used by your existing runner; selecting a messageboard backend does not create an attacker model.

The `run` and `observe` commands accept `--messageboard swarmchat`. Their default remains `memory` for compatibility. For example, on the Linux host required by the target launcher:

```bash
uv run --extra swarmchat python -m adaptivehoneypotenv run \
  --defender live --messageboard swarmchat \
  --attacker-max-tokens 1024 --defender-max-tokens 1024 --max-cost-usd 5
```

This needs the existing controller's `OPENROUTER_API_KEY` and Docker/iptables setup. `run --defender live` continues through the full episode, with a new defender decision after each attacker window. It stops on termination, external cutoff, or an invalid transition and prints a JSON summary with the reason and transition count. A valid terminated or truncated run exits with code 0; an invalid run exits with code 1. Neither status implies a defender win. Ctrl-C requests an operator kill, closes the target and viewer, and exits with code 130. `observe` and `run --defender scripted` remain defender-only smoke paths without attacker models, so they do not create team conversations by themselves.

Reset prints the private SwarmChat data directory. Open its native viewer in another terminal:

```bash
uv run --extra swarmchat swarmchat view --data /path/printed/by/the/controller
```

While the episode is open, this connects to the managed loopback viewer. After `close()`, the same command can open the saved SwarmChat log as an offline view. The native viewer is supplementary: the existing React/PixiJS observer and episode journal remain the source for experiment outcomes, provenance, and recorded trajectory playback. SwarmChat's “as an agent” views show channel membership and cumulative read positions, not the model's exact round-filtered observation history; use the episode journal for that history.

## Semantics preserved

| Experiment contract | Integration behavior |
|---|---|
| One board per episode | A fresh private SwarmChat store, one `#attackers` channel, and one user per attacker |
| Explicit, charged communication | Actors still call only `post_to_messageboard` and `read_messageboard`; each costs an attempt |
| No same-round reads | The controller filters by committed episode post ID and strictly earlier round before reading stored messages |
| No pushed messages | No SwarmChat notifications, waits, or read receipts are injected into model histories |
| Bounded exact content | Existing 2,000-character post and 20-post/16-KiB read limits; UTF-8 and whitespace preserved |
| Hidden from defender | Board activity and content use the existing private projections; native viewer access is operator-only |
| Existing action/event schemas | No new model tools, schema versions, scheduler, or reward changes |
| Failure is not attacker failure | Store or receipt errors invalidate the episode; no silent memory fallback or automatic post retry |

SwarmChat is the storage backend, not merely an outgoing mirror. Each actor board read retrieves the selected posts from its log and verifies their identity, round, and exact text against the committed catalogue. The catalogue retains IDs/content for clipping and integrity checks; the model receives no native SwarmChat metadata.

Posts use the pinned `Chat.append` primitive with episode post/round metadata. The upstream `send` API rejects whitespace-only text that our frozen schema permits. This narrow adaptation preserves the original bytes without changing the tool schema. Upstream source files are unmodified. Future upgrades must re-run backend parity and viewer tests.

## Persistence and access

Data is under `runs/<profile>/<episode-id>/private/swarmchat/` (or the equivalent custom run root), outside the actor workspace. The directory is mode `0700`; tokens and the integration record are private files. `integration.json` records the episode, backend version/revision, channel, and visibility policy. Include this sidecar with private run artifacts; it does not extend the frozen manifest schema.

The store is embedded in the controller; only an authenticated **viewer** listener binds to `127.0.0.1` on an allocated port. Agent/admin HTTP operations are denied even with a valid token. Actors receive neither SwarmChat credentials nor a shell/client endpoint. No SwarmChat port is published on the target network, and the target containment configuration is unchanged.

The gateway journals results before returning them. It commits a post to SwarmChat before acknowledging success and updates native read positions only after the read result is journaled. A cursor read that skips earlier messages does not falsely advance a cumulative receipt across them. These receipts are supplementary; exact delivered post IDs come from the episode journal.

There is no distributed transaction between the two logs. A failure after either write invalidates the episode; a crash never resumes a scored run against uncertain state. A saved store cannot be reused as a new episode. Reset/close and failed setup stop the viewer and release the store. Saved data remains available for inspection.

## Verification

```bash
uv run --extra swarmchat pytest tests/test_swarmchat.py
uv run --extra swarmchat ruff check .
uv run --extra swarmchat ruff format --check .
uv run --extra swarmchat mypy
```

Tests use the real SwarmChat store and authenticated HTTP viewer. They cover backend parity, same-round visibility, explicit reads, clipping, private projections, exact text, cursor receipts, write/read/journal failures, episode isolation, and resource cleanup. Lifecycle tests mock the target launcher and are not containment evidence. No model API calls are needed. CI installs the optional extra and runs the full suite on Linux with Docker and iptables.
