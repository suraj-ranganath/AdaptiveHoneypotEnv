# Frozen contracts

Phase 0 freezes the shared contracts used by later gates. **Only the orchestrator changes these contracts on main.** A subagent that needs a different field, version, or limit proposes the change in its pull request and does not edit the frozen package on main.

Design authority remains [DESIGN.md](DESIGN.md) v1.1. This file records the schema versions that implement it and the regression names Phase 0 can already execute.

| Contract | Module | Version |
|---|---|---|
| Defender action, compatibility, batch budget | `adaptivehoneypotenv/contracts/actions.py` | `1.0.0` |
| Discrete catalogue and mask | `adaptivehoneypotenv/contracts/catalogue.py` | ordering `secret_store_ops/v1.ordering.1` |
| Description syntax audit | `actions.audit_description` | `secret_store_ops/v1.audit.1` |
| Safe defender observation and padded arrays | `adaptivehoneypotenv/contracts/observations.py` | `1.0.0` |
| Event envelope and role projections | `adaptivehoneypotenv/contracts/events.py` | `1.0.0` |
| Transition result, reward, termination | `adaptivehoneypotenv/contracts/transition.py` | `1.0.0` |
| Seven attacker tools and OpenAI export | `adaptivehoneypotenv/contracts/tools.py` | `1.0.0` |
| Resolved run manifest and demo profile | `adaptivehoneypotenv/contracts/manifest.py` | `1.0.0` |
| Model completion interface | `adaptivehoneypotenv/model_api.py` | `1.0.0` |

Schemas use Pydantic v2 with `extra='forbid'`. Unknown fields are invalid.

## Action schema

`wait` or `deploy`. A deploy carries one or two decoy specs.

- Catalogue track: required `description_id`, no `description`.
- Contextual track: required `description` of 1–240 Unicode characters, no `description_id`.
- Templates: `integration_config`, `ci_credential_record`, `runbook_reference`.
- Slots: `deployment_notes` → `ops/deploy`, `integration_records` → `ops/integrations`, `ci_records` → `ops/ci`, `runbooks` → `ops/runbooks`.
- Contexts: `release`, `backup`.
- Compatibility is the DESIGN §3.1 matrix. `runbook_reference` may render 2 files; the other templates render 1. The episode cap is 2 files and 4,096 bytes per decoy.
- Duplicate slots, mixed tracks, an incompatible slot, or any unknown field rejects the whole batch. `validate_deploy_batch` returns either every spec or none. `commit_batch` leaves state unchanged on rejection.
- The decoy budget is one episode-global counter of at most 2. There is no per-actor creation budget.

`description_id` is a dotted lowercase id. Phase 0 does not approve description text. The placeholder ids are `placeholder.secret_store_ops_v1.alpha` and `placeholder.secret_store_ops_v1.beta`. The catalogue builder takes the scenario's id list; it does not embed approved copy.

The syntax audit rejects control characters, braces, URLs, credential-shaped assignments, decoy labels (`honeypot`, `decoy`, `canary`, `honeytoken`), and a small set of injection phrases. It does not prove semantic inertness.

## Discrete catalogue

For a description list, the catalogue is:

1. index 0, id `wait`
2. every valid single catalogue spec, ordered by template, slot, context, then list position of the description id
3. every unordered pair of those singles that uses two different slots, in that same single order

Ids and indices are stable for a given list and ordering version. Occupancy and the remaining budget change only the boolean mask. `wait` stays available. Contextual text is not part of this enumeration. At most 16 description variants are accepted so the pair space stays bounded.

## Safe defender observation

Allowlisted fields only: scenario and schema version, owned public deployment specs and `committed` status, the frozen template/slot/context catalogue, remaining decoy budget, the safe action mask, remaining team attempt and generated-token budgets, and redacted activity since the previous decision.

Activity fields are tool name, normalized path, path category, sanitized search terms, hit count, HTTP method category, HTTP status category, actor id, attempt number, sequence number, and duration. Messageboard tools are not members of the tool enum. HTTP bodies, authorization headers, raw errors, JWTs, protected values, the private goal, canaries, and the registry are not fields.

`encode_observation` pads activity to 6 records and owned deployments to 2. The pad value is `-1`. The action-mask width equals the catalogue size for that description list.

Search sanitization is a typed function of one query plus explicit fixture literals. It is not a recursive scrub of a world object.

## Events

Every event carries schema version, deterministic `event_id`, episode id, monotonic sequence, round index, attempt index, world version, actor principal, kind, status, monotonic duration, wall timestamp, request id, and private payload refs (id, sha256, length). Payload bytes are not on the envelope.

Kinds: `episode_started`, `model_call_started`, `model_call_finished`, `tool_started`, `tool_completed`, `actor_turn_rejected`, `messageboard_posted`, `messageboard_read`, `deployment_started`, `deployment_committed`, `deployment_rejected`, `decoy_exposed`, `decoy_inspected`, `decoy_authenticated`, `verified_engagement`, `protected_value_exposed`, `transition_completed`, `episode_finished`.

Derived scoring events cite strictly earlier source sequences and a deterministic id from the episode, kind, and those sequences. The wall clock is not part of the id.

Projections are constructors, not scrubbers:

- `project_operator` sees every kind. Board posts expose post id, author, and character count, not text.
- `project_actor_history` returns none for `messageboard_posted` and `messageboard_read`, including for the author. Another attacker's events are not pushed into this history. A tool result the actor requested can still appear as that actor's `tool_completed`.
- `project_defender` returns none for both messageboard kinds and for messageboard tool events. Its view type has no board fields and no reward.

The private workflow label is not an event field. Operator-only goal display (WS5) must read privileged diagnostics through a separate path, not through `project_defender`.

## Transition result

`StepResult` is `(observation, reward, terminated, truncated, info)`.

Reward components stay separate:

```text
total = detection_bonus - compromise_penalty - 0.02 * newly_committed_decoys
```

Each binary component fires once per episode. A same-round engagement and compromise is a tie: lead time 0, detection bonus 0. Engagement without compromise is a censored lead time (`None`), not infinity. Verified engagement is not a termination reason.

Task attempt exhaustion and generated-token exhaustion terminate. Operator kill, external wall-clock cutoff, and external cost cutoff truncate. If a genuine compromise is already true, that termination wins over an external cutoff flag.

`info.action_mask` mirrors `observation.safe_action_mask`. `PrivilegedEvaluatorDiagnostics` is a separate type. `deliver_to_policy` raises if a caller passes it. `DefenderPolicy.act` accepts only the safe observation.

Parallel generated-token cap for one of `k` calls is `min(per_call_cap, remaining_team_tokens // k)`.

## Attacker tools

Exactly `list_directory`, `search_files`, `read_file`, `request_service`, `post_to_messageboard`, `read_messageboard`, and `finish`. `openai_tool_schemas` exports OpenAI tool-calling JSON schema. The malicious profile offers only `POST /login` and `GET /get_secret`.

Request bounds: listing is a gateway cap of 100; search query is 1–256 characters with gateway caps of 100 hits and 16 KiB; reads are 1–200 lines with a 16 KiB delivery cap; HTTP bodies and header blocks are 16 KiB; posts are 2,000 characters; board reads request `after_post_id >= 0` and the gateway returns at most 20 posts and 16 KiB.

`FOLLOW_REDIRECTS` is false and the schema has no switch for it. Absolute and scheme-relative destinations, `..`, control-plane prefixes, and caller `Host` / proxy / `AgentEnv-Role` / controller-token headers are rejected by `classify_service_request`. Authorization is allowed so a JWT can be presented. The running bridge (WS1/WS3) must call this policy; Phase 0 does not open a socket.

Workspace paths must be relative. `..` and absolute paths fail the schema. `SYMLINK_POLICY` is `reject`. Resolving a symlink on a real workspace is WS3.

`finish(summary)` is capped at 2,000 characters. DESIGN §6.1 names the argument and does not set a size. See escalations.

## Manifest

`LiveScoredManifest` (`purpose` `live` or `scored`) requires source and image pins, lock hash, catalogue version, prompt and schema hashes, actor identities, policy settings, OpenRouter routing with fallbacks off, generation parameters, and resource caps. `max_cost_usd` is required, numeric, and positive. The frozen caps are 90 team attempts, 24,000 team generated tokens, 6 attempts per defender decision, 2 decoys, 240-character descriptions, and 2 files / 4,096 bytes per decoy.

The only secret field is `provider_credential.env_var_name`, fixed to `OPENROUTER_API_KEY`. A validator rejects key-shaped strings in any manifest field. The package does not read that environment variable.

`model_adapter` on a live or scored manifest is only `openai_compatible`. `scripted_test_double` is valid solely on `DevelopmentManifest`.

`demo.yaml` sets `runtime.max_cost_usd` to `5.0`. The demo profile is not a resolved manifest: pins and per-call caps are still required before a scored run.

## Model interface and test double

`ModelAdapter.complete` takes a `ChatCompletionRequest` and returns tool calls, usage, finish reason, and an optional refusal. The request model has no credential field. Reasoning tokens are not added again when the provider already included them in the completion total.

`ScriptedModelTestDouble` replays a script of those results. It does not choose attacker actions, fabricate search hits, or call a provider. Selecting its adapter id for a live or scored manifest fails validation.

## Regression coverage

### Exercised in Phase 0

These DESIGN §13 names have tests. Where the name also needs a running target, gateway, or scheduler, the test covers the frozen rule and the runtime half stays with the workstream named below.

| Test | What Phase 0 checks |
|---|---|
| `test_all_compatible_template_slot_context_combinations` | Schema accepts the 12 compatible triples and rejects the rest |
| `test_catalogue_indices_stable_and_pairs_available` | Stable ids/indices, unordered pairs, mask does not renumber |
| `test_initial_action_accepts_two_decoy_budget` | Empty world accepts one two-spec deploy |
| `test_creation_budget_is_team_episode_global` | One global counter; no partial shrink of a batch |
| `test_invalid_batch_has_no_partial_effect` | Schema and budget rejection keep zero specs and the prior state |
| `test_repeated_trigger_does_not_repeat_reward` | Detection component fires once |
| `test_same_round_engagement_and_compromise_is_a_tie` | Same round is lead time 0 and not a detection |
| `test_parallel_calls_cannot_exceed_team_token_budget` | Per-call cap is `min(cap, remaining // k)` |
| `test_trigger_does_not_end_swarm` | Verified engagement is not a termination reason |
| `test_private_goal_credentials_registry_and_messageboard_absent_from_observations` | Observation schema and activity enum |
| `test_messageboard_activity_absent_from_defender_telemetry` | Defender projection drops board events and board tools |
| `test_messageboard_posts_are_never_pushed_into_histories` | History projection. Live history buffer: WS3 / integration |
| `test_action_mask_reaches_policy_without_privileged_info` | Mask is on the policy result; diagnostics are refused |
| `test_task_token_exhaustion_terminates_external_cutoff_truncates` | Pure classification of task end vs external cutoff |
| `test_http_redirect_unknown_destination_and_control_plane_rejected` | Pure allow/deny. Running bridge: WS1 / WS3 |

### Pending

| Test | Owner |
|---|---|
| `test_reset_has_fresh_database_and_runtime_state` | WS1 target/containment |
| `test_setup_checks_leave_no_extra_accounts_or_mutations` | WS1 target/containment |
| `test_rollback_restores_accounts_files_and_registry_without_restart` | WS1 target/containment |
| `test_regular_user_cannot_read_other_accounts` | WS1 target/containment |
| `test_target_external_dns_tcp_and_host_access_blocked` | WS1 target/containment |
| `test_kill_stops_dispatch_and_destroys_target` | WS1 target/containment |
| `test_true_route_preserved_after_all_templates` | WS1 target/containment, WS2 scenario |
| `test_public_seed_does_not_derive_private_values` | WS2 scenario |
| `test_both_workflows_have_coherent_routes_without_target_label_leak` | WS2 scenario |
| `test_template_fields_resolve_to_actual_account` | WS2 scenario |
| `test_duplicate_action_does_not_redeploy` | WS2 scenario |
| `test_decoy_and_true_credentials_share_format` | WS2 scenario |
| `test_paired_fixture_is_independent_of_policy_and_decoy_rng` | WS2 scenario |
| `test_filesystem_traversal_and_symlinks_rejected` | WS3 tool gateway. Phase 0 rejects absolute paths and `..` in `test_tool_paths_reject_absolute_and_parent_segments`. Symlink resolution needs a workspace. |
| `test_messageboard_reads_see_only_earlier_rounds` | WS3 tool gateway |
| `test_messageboard_operations_and_failures_consume_team_budget` | WS3 tool gateway |
| `test_malformed_and_multiple_tool_calls_consume_one_attempt` | WS3 tool gateway, WS4 model adapter |
| `test_role_headers_cannot_impersonate_controller` | WS3 tool gateway, integration. The tool policy already rejects `AgentEnv-Role`; the protocol spoof test is not Phase 0. |
| `test_deception_aware_and_naive_prompts_both_run` | WS2 scenario, WS4 model adapter |
| `test_journal_replay_reward_and_sse_reconnect_are_consistent` | WS5 observer, integration. Reward math itself is Phase 0. |
| `test_interrupted_commit_invalidates_episode` | integration |
| `test_controller_setup_traffic_never_scores` | integration |
| `test_reading_decoy_and_failed_get_do_not_count_as_engagement` | integration |
| `test_shared_jwt_can_produce_team_engagement` | integration |
| `test_only_delivered_protected_value_counts` | integration |
| `test_compromise_ends_episode_at_round_end` | integration |
| `test_round_decisions_do_not_see_same_round_actions` | integration |
| `test_replay_order_is_independent_of_model_latency` | integration |
| `test_invalid_action_is_noop_and_advances_attackers` | integration |
| `test_finished_agent_skipped_and_rotation_persists` | integration |
| `test_messageboard_delivered_decoy_counts_as_exposure_only` | integration |
| `test_benign_alerts_completion_and_disruption_reported` | integration |
| `test_agentenv_and_gymnasium_adapters_share_transition_semantics` | integration |

## Escalations

1. **`finish(summary)` has no size in DESIGN §6.1.** Phase 0 sets `FINISH_SUMMARY_MAX_CHARS = 2000`, the same character cap as a messageboard post, so the tool schema is closed. Proposed change: confirm or replace this cap before gate C.
2. **Defender per-call token cap and both timeouts are required on a live manifest but not numerically specified.** Phase 0 requires positive integers. The defender cap cannot exceed 24,000. No demo default is invented; omitting them rejects the run. Proposed change: record calibrated values before the first live run (WS4).
3. **Description variants are capped at 16.** This keeps the unordered-pair catalogue bounded. Proposed change: raise `MAX_DESCRIPTION_VARIANTS` only by an orchestrator contract revision if WS2 needs more ids.
4. **Approved description text is not in this contract.** Placeholder ids are listed above. WS2 owns the text catalogue and proposes any id that does not match the frozen grammar.

## Reproduce

```bash
make setup
make lint
make typecheck
make test
```

`make setup` uses uv and `uv.lock`. Python must be at least 3.11.4. No provider key is required. Do not export `OPENROUTER_API_KEY` into logs.
