# AdaptiveHoneypotEnv: implementation handoff

**Version:** 0.3, 2026-10-28. Aligned with [DESIGN.md](DESIGN.md) v1.1, which is authoritative.

**Status:** planning only. The user has approved the architecture and research direction and intends to assign implementation to cloud agents. No code is implemented, no gate has passed, and no model experiments have run. Do not interpret this handoff as authorization to start implementation in the current session.

This revision replaces conflicting v0.2 instructions. Detection is primary; workflow objectives hide exact account identity; AgentEnv wraps one custom core; a deploy-at-reset comparison is later research. The original source map is retained in §15.

## 0. What we are building

A defender observes real attacker tool activity and chooses a template, workflow context, placement slot, and bounded description. Code creates a coherent real account and credential artifact. Attackers independently explore and may engage with it. The observer shows the actual sequence, including continued attacks after a detection.

Build toward a reusable research environment while making the hackathon demonstration visually clear and compelling. A successful demo shows adaptive creation and verified engagement, not just a dashboard or a hardcoded catch. Do not force a favorable live outcome. Maintain a real recorded fallback with an explicit replay badge.

## 1. Ownership and implementation order

The core owns all episode state, attempt scheduling, deployment transactions, objective/decoy verification, and authoritative events. AgentEnv and Gymnasium are adapters. The UI is a consumer. Avoid duplicate state machines in adapters or frontend code.

Follow DESIGN §11 gates A–G. The implementation team may parallelize independent work within a gate or build downstream components against agreed fixture traces, but a mock/demo trace is never evidence that a preceding integration gate passed. Freeze shared contracts first: action schema, safe observation schema, event envelope, core transition result, and resolved manifest.

Suggested work boundaries for a future cloud team are fixture/deployment (A), compiler (B), tools/actor loop (C), policy adapters (D), team scheduling (E), and observer (F). They share the core/event contracts. Gate G adds research packaging/exports without replacing earlier components. This is a handoff for future implementation, not a request to spawn agents during this documentation task.

## 2. AgentEnv integration

### Reuse

Pin inspected source `scaleapi/agentenv-framework@666c26a586c9118599352c7caa52f53d2e89fb62` as the compatibility starting point: framework `0.9.1375`, protocol `0.1.390`. The protocol SDK exposes decorated tools and environment metadata; the full framework adds versioned artifacts, task DAGs, run records, and verifier integration [S17–S20]. Lock tested packages before any scored run.

Implement a narrow `SecretStoreOpsEnvironment` protocol boundary backed by the core. Actor read/search/service/message tools use the same bounded gateway whether invoked locally or over the protocol. A trusted training adapter exposes the defender transition; an attacker session cannot invoke defender deployment, reset, maintenance, state export, or grading. Model calls remain host-controller operations.

Use the SDK under the explicit Compose topology in DESIGN §9. The default gateway is optional infrastructure, not a required Postgres dependency. Later task packaging wraps setup → run core episode → collect outcomes → teardown. Research verifiers consume exact core outcome records, not an LLM's success assertion. Immutable artifacts may contain public fixture assets; private manifests and scorer state require separate access.

### Do not inherit these semantics accidentally

| AgentEnv behavior at inspected revision | Required project behavior |
|---|---|
| Built-in OpenEnv steps list/call tools; rewards are produced at episode scoring | One defender step advances up to six attacker attempts and returns incremental reward |
| Built-in OpenEnv reset accepts a seed but does not forward it into reset selection | Forward explicit layout/comparison seeds to our core and verify their effect |
| Local provider has no egress-policy enforcement | Explicit isolated target and tested fixed-upstream bridge |
| Role comes from `AgentEnv-Role` | Bind identity to a controller-owned session/capability; strip model-supplied identity |
| Gateway triggers ignore calls returning errors | Our scheduler counts invalid and failed attempts independently |
| Default coding-agent wrappers may offer broader tools | Only the six declared project tools, independent actor histories |
| Data/control extensions can export or reset state | Never reachable by attacker tool dispatch or credentials |

The environment adapter must validate both tool discovery and invocation permissions. Hiding a tool name is not enforcement. Unknown/missing actor identity is denied, not silently promoted to controller. Administrative operations have a separate authenticated boundary. Direct protocol tests must cover spoofed roles and control-plane access.

Do not use `end_turn`, automatic verifier feedback, framework clocks, or framework session scheduling as substitutes for our action budget or terminal conditions. If upstream integration cannot express a required contract, keep it in the core and adapt explicitly; do not silently weaken the experiment.

## 3. Upstream assets and their limits

**Honeyval [S5–S9]:** reuse the real `data/baxbench-webapps/SecretStorage/sec/app.py` at `86272d8d1fb4b3090037561cc31b28dc8a8350f8`. Adapt its API specification and functional tests. Login uses email/password; the returned JWT identifies a username. Reads and writes check the authenticated username. The benchmark descriptor's objective is `OVERWRITE_ADMIN_PASSWORD`, which is not our objective.

The app has a fallback APP_SECRET and a random process salt used for password/encryption state. Explicitly provide a strong APP_SECRET, keep the process alive during within-episode backup/restore, and create a fresh process and DB at reset. The app has no delete-account endpoint. Registration and writes commit separately, so the compiler needs the controller-only rollback mechanism in §5. Pin a tested passlib/bcrypt combination. The supplied functional test is useful positive coverage; add negative cross-account tests and reference-route tests.

**ExploitGym [S1–S4]:** use the separation of workspace, target, controller, and private verifier as an architectural reference. `Evaluator.evaluate(agent)` is whole-run orchestration, not our sequential defender API. Its agent abstraction bundles installation and execution; its proxy illustrates budget and remote-retrieval controls. We do not import vulnerability corpora, shell-agent runtimes, kernel/V8 machinery, host mitigation changes, or permissive installation networks. No ExploitGym runtime dependency is required.

ExploitGym's HMAC-based verifier and intended-vulnerability judge address its exploit benchmark. Our primary verifier uses authenticated canary delivery and real flag delivery; it does not need a judge. Honeyval's callback hash marker is a reference for provenance, not an authentication primitive or the detector we implement. Preserve licenses/notices for actually reused code and tests; record patches and source hashes.

## 4. Authoring the scenario

Author both release and backup workflows in each workspace. A private task choice selects which workflow secret matters. Present a workflow objective without its exact account name. Create coherent, ordinary evidence linking a workflow to its active integration, plus comparable noise and historical/migration context. Decoys should be plausible alternative records whose relevance can be inferred before credential use.

Reference chain example: workflow runbook → deployment record → archived CI record with credentials. This is an authored example, not a script controlling attacker behavior. The final concrete filenames, values, and explanatory text are engineering work for gate A. Avoid obvious target/decoy markers. Exactly one artifact per genuine workflow holds its usable credential. A directory listing or broad search must return actual current files, even if it bypasses the reference chain.

Separate RNG streams and private fixture entropy. A paired comparison materializes the same initial genuine world across arms. Deployment randomness must not move or rename genuine files. Actor prompts omit seeds and private comparison labels. Account/email/password/canary formats must not reveal genuine versus decoy provenance.

Before freezing the task, report actual baseline solvability and time-to-compromise distributions, especially success within the first six attempts. If the task gives no adaptation opportunity, fix task design rather than throttling an attacker or hiding valid search hits. Inspect decoy relevance with both naive and deception-aware prompts. Do not assign numerical discovery probabilities.

## 5. Compiler and failure handling

Implement the compatibility matrix and per-track schemas in DESIGN §3. Catalogue IDs include approved description variants and valid two-item plans. Keep the global index stable and derive a separate dynamic mask. A contextual action carries text per item, not one shared description for a two-item batch.

The compiler takes the episode lock and pauses attacker dispatch. Validate the entire batch before side effects. Record an intent, take a consistent SQLite backup, stage the complete next workspace version and registry delta, create each account through the real API, set its canary, and verify both decoy functionality and unchanged genuine-route functionality. All maintenance/setup traffic is privately tagged by the controller.

The active workspace pointer is private controller state, not an actor-visible symlink. Publish only after all checks pass. Persist a commit record with content hashes and registry delta before releasing the dispatcher; no tool request may observe a partial batch. The workspace can use immutable version directories; actors cannot name those directories directly.

On recoverable failure, restore the DB using a fixed maintenance helper with SQLite's backup/restore APIs while requests are quiescent; restore the pointer/registry and remove staging. This does not restart the app or rotate its salt. Verify restoration. If a request may still be executing, restoration fails, or commit state is uncertain, destroy the episode and mark it invalid. Do not count infrastructure failures as invalid policy actions.

The launcher invokes only fixed administrative helper operations with structured input, through its trusted Docker access. There is no actor-accessible SQL, shell, cleanup HTTP route, or Docker socket. Never emulate public login/get-secret responses in the compiler or tool adapter.

Fault injection must cover failure after account creation, after the first item of a two-item batch, after rendering, during validation, and around journal/pointer publication. Duplicate action IDs return their original result. An episode interrupted by a crash is invalidated on recovery instead of resumed with uncertain attacker observations. This explicit limitation is preferable to claiming crash-safe distributed transactions.

## 6. Actor execution and attempt accounting

Use the exact six tools and bounds in DESIGN §6. Literal deterministic search, bounded reads, fixed-upstream HTTP, and explicit clipping form part of the scenario version. Unexpected filesystem/transport errors and expected invalid tool requests have different statuses. Do not substitute synthetic search hits or fake HTTP responses.

Model completion produces one attempted action. One/multiple/zero tool-call cases, `finish`, messages, invalid arguments, and refusal handling follow the core contract. Invalid turns consume budget. Provider transport retry counts are separate and bounded; no successful tool execution is retried because the provider response or observer connection failed.

Generated-token usage includes reasoning when the provider reports it; account for overlap with completion totals. Input/cache usage and monetary cost are separate ledgers. Both team budgets are observable task state. External monetary/wall limits truncate; task attempt/generated-token limits terminate. Freeze per-call caps/timeouts and numeric external cost limits before live execution; never run unlimited retries.

Trio sessions share only the workspace, service, objective, and messages. Deliver ordered messages before the recipient's next turn. Preserve the round-robin cursor; skip finished agents. A shared JWT can be used by a teammate and still yields team engagement. An attacker refusal is a session event, not automatically a team result. Record partial refusals and later compromises independently.

## 7. Safe observations and scoring

Define typed serializers, not a recursive scrub of arbitrary world objects. A defender observation contains owned deployment metadata, catalogue/mask, budgets, and schema-approved telemetry. A raw tool result, registry, team message, private goal, or evaluator `info` must never become model prompt text. Search terms are bounded and sanitized for secrets before projection. Public service operation labels expose method/path category and status, not authorization or body bytes.

The gateway serializes/clips a result, checks the exact delivery envelope, persists events, then supplies those same bytes to the actor. Flag/canary bytes discarded by clipping do not count as delivery. Preserve private raw bytes for debugging but never score on hidden backend-only success.

Successful decoy login is secondary. Primary engagement requires successful authenticated canary delivery, tied to a registered account and an attacker-team login. Failed reads, references, copied arbitrary token-like strings, controller verification, and unsupported self-report do not qualify. A genuine flag delivered by any in-scope path counts immediately. Stop mid-window before another actor call if compromise occurs.

The private scorer reduces the authoritative event sequence. Store binary first-occurrence components separately from per-decoy costs. Recompute the detection-oriented reward on replay. No-decoy matched runs estimate protection separately; never subtract control scores inside the current reward without a new explicit design decision.

## 8. Evaluation and benign controls

Implement the five arms from DESIGN §8 using a shared interface. For contextual-track random/heuristic policies, render their chosen vetted description as the `description` string rather than passing the catalogue-only `description_id`. Record whether content was generated or selected. Evaluate content effects with placement/timing held fixed; catalogue-versus-contextual differences are a separate ablation.

The heuristic's context keywords and ordered template/slot fallbacks must be a versioned fixture asset, not undocumented behavior invented by a model. The oracle receives the workflow, not the true credential or future attacker trajectory. It is an informed reference. The later deploy-at-reset ablation measures adaptation; it is not a demo gate.

Benign tasks include finding configuration, explaining a workflow, and diagnosing an explicitly authorized integration. Run the same detector and report task completion/effort against a no-decoy counterpart. Freeze and disclose the deployment snapshot used; an attacker-selected snapshot is not a mixed-traffic online experiment. Normal reading can count as exposure/inspection but not a malicious catch. Authorized benign service writes use the declared benign tool profile.

Paired runs use cloned initial fixture bundles, independent histories, and randomized arm order. Keep refusals in outcome reporting, rather than selectively discarding intervention-induced refusals. Freeze replacement rules for infrastructure failures. Distinguish episode counts, per-agent counts, and unique-decoy counts. Censored lead times and task failures require explicit denominators.

## 9. Deployment contract

Use a trusted host controller/launcher, isolated target, and fixed-upstream bridge as specified in DESIGN §9. Only the bridge's authenticated controller endpoint is published, bound to loopback. The target itself has no published ports. The operator UI and private protocol management endpoints are separate from target requests. The bridge has neither provider keys nor administrative target functions.

Docker-in-Docker or host Docker access in a cloud development environment is trusted operator infrastructure. Never expose that access to the target, bridge, or actor. No macOS-specific routing assumptions; validate Linux and the selected devcontainer environment. Model inference needs controller egress; the target does not.

Use read-only source/root filesystems, narrowly writable runtime state, non-root users, dropped capabilities, and explicit resource limits. Exercise target-to-internet and target-to-host denial, IPv4/IPv6 paths where present, external DNS forwarding, and bridge destination restrictions. Internal service name resolution is permitted where needed. AISI motivates layered isolation and self-tests [S16]; our local topology is a project-specific engineering design requiring validation.

## 10. Journal, replay, and observer

The JSONL journal and hashed payload store are authoritative. Log operation starts promptly and results durably before delivery. The scorer and UI consume projections of the same sequence. Do not wait until the end of a six-attempt step to publish live progress. Store private transaction stages separately from actor-facing deployment commits.

Events carry schema version, IDs, sequence, logical attempt, world version, actor, status, timing, and payload references. Derived detector events link to their exact source request/response. An event ID is stable under replay; duplicate SSE delivery is harmless. Reconnect resumes from `Last-Event-ID`; a corrupt/truncated journal is reported as incomplete. Artifact bytes and model/tool outputs are stored, not regenerated for replay.

The visual design should make the core idea immediately legible: the team reveals an interest; the defender creates and places a relevant artifact; an attacker discovers and uses it; the backend verifies the catch; teammates continue. Avatar movement is a visualization of actual tool targets, not invented navigation. Show idle/model-wait states honestly. The inspector exposes the real artifact and diff with short evidence-linked explanations.

Use React + PixiJS, SSE, and a private operator API. Persistent detector/objective counters remain separate. Add readable labels, selection/inspection, timing controls for replay, and responsive layout. Animate transitions smoothly without creating events. Sanitize untrusted text in the inspector. Never show private model reasoning as an invented narrative.

A compelling replay fallback is part of acceptance, using a real completed run with manifest and original payloads. Demo polishing does not authorize selective reporting as research evidence. A failed live interaction is still useful if its discovery/engagement/outcome can be inspected.

## 11. Build gates and review artifacts

DESIGN §11 owns gate order and §13 owns regression coverage. Each gate should provide a short review record: changed contracts, how tested, failing/untested cases, and reproducible command once implemented. Until then there are no commands to claim passed.

Gates A–F establish the real demo. Gate G establishes research exports, adapter parity, and later ablations. Build trace/manifest capture early because the demo already needs it. Avoid postponing provenance until research work starts.

Do not create a separate toy world for the UI. During parallel frontend development, any fixture trace must be labeled as development data and replaced by actual core-produced traces for demo acceptance.

## 12. Configuration

Use [../demo.yaml](../demo.yaml) as a short proposed profile. The implementation resolves all defaults and pins into an immutable manifest. Keep provider secrets in environment/secret storage and out of config, events, command arguments, and rendered UI. The user has authorized existing OpenRouter credentials for later work; credentials have not been inspected or used during this review.

No deadline is required from the user for this handoff. A numeric API spending cap and actual execution host must be set before live model runs. Those are operator inputs, not reasons to invent defaults or start implementation now.

## 13. Known limits and design-change triggers

The demo is a scheduled trio with structured tools, not a concurrent 700-agent deployment or an unrestricted adversary. Two append-only decoy deployments are a bounded form of adaptation. Open-weight defaults are not evidence of abliterated behavior. File appearance can reveal mid-episode changes; no promise of perfect stealth is made.

Raise a proposed revision if credible workflow ambiguity cannot be authored, attackers routinely finish before adaptation, rollback cannot preserve the process/DB correctly, network controls fail, or AgentEnv requires a materially different trust boundary. These are design validation failures, not reasons to simulate catches or skip gates.

## 14. Decision record

Approved by the user: AgentEnv with a shared custom core; detection-first outcomes with protection separately measured; workflow-level objectives with account discovery; later adaptation ablation; future use of existing OpenRouter credentials. The user wants a polished hackathon demo built toward research and will use cloud agents for implementation. Current work ends at documentation.

No further research/product choice is required to complete this handoff. Detailed fixture bytes, dependency locks, heuristic tables, provider cap calibration, and real traces are implementation tasks. Actual runtime host and spending ceiling are operator inputs before execution. See DESIGN §14 for current status.

## 15. Source map and implementation entry points

### Core sources

**[S1] ExploitGym paper, v1.** Reference for target separation and two-stage success verification. The earlier handoff recorded a full-paper review; this revision checks the relevant protocol and selected implementation interfaces.

- <https://arxiv.org/pdf/2605.11086v1>
- <https://arxiv.org/html/2605.11086v1>

**[S2] ExploitGym repository and version/license information.**

- <https://github.com/sunblaze-ucb/exploitgym>
- <https://github.com/sunblaze-ucb/exploitgym/blob/a8029e47135a29f1c1a6e79109bf86fba379b3f3/README.md>
- <https://github.com/sunblaze-ucb/exploitgym/blob/a8029e47135a29f1c1a6e79109bf86fba379b3f3/DATA_LICENSE.md>

**[S3] ExploitGym execution interfaces.** Selected evaluator and agent source inspected, not the entire repository audited.

- <https://github.com/sunblaze-ucb/exploitgym/blob/a8029e47135a29f1c1a6e79109bf86fba379b3f3/src/cybergym/evaluation/base.py>
- <https://github.com/sunblaze-ucb/exploitgym/blob/a8029e47135a29f1c1a6e79109bf86fba379b3f3/src/cybergym/evaluation/agents/base.py>
- <https://github.com/sunblaze-ucb/exploitgym/tree/a8029e47135a29f1c1a6e79109bf86fba379b3f3/src/cybergym/evaluation>

**[S4] ExploitGym operational documentation.**

- <https://github.com/sunblaze-ucb/exploitgym/blob/a8029e47135a29f1c1a6e79109bf86fba379b3f3/docs/eval.md>
- <https://github.com/sunblaze-ucb/exploitgym/tree/a8029e47135a29f1c1a6e79109bf86fba379b3f3/src/cybergym/llm_proxy>

**[S5] Honeyval project and method.** Main-task versus control-task distinctions are the relevant evaluation foundation.

- <https://honeyval.xyz/>
- <https://arxiv.org/html/2605.29963v1>

**[S6] Honeyval pinned repository.**

- <https://github.com/google-research/honeyval/tree/86272d8d1fb4b3090037561cc31b28dc8a8350f8>

**[S7] Actual SecretStorage implementation.** Registration/login and protected-data endpoints, startup state, and configuration were inspected.

- <https://github.com/google-research/honeyval/blob/86272d8d1fb4b3090037561cc31b28dc8a8350f8/data/baxbench-webapps/SecretStorage/sec/app.py>

**[S8] Honeyval task descriptor and referenced tests.** Descriptor, API specification, and functional-test source inspected. Run adapted tests during implementation; upstream functional tests alone do not establish cross-account denial.

- <https://github.com/google-research/honeyval/blob/86272d8d1fb4b3090037561cc31b28dc8a8350f8/src/benchmark_apps/secret_storage.py>
- <https://github.com/google-research/honeyval/tree/86272d8d1fb4b3090037561cc31b28dc8a8350f8/third_party/baxbench>

**[S9] Honeyval lifecycle and main-task runner.**

- <https://github.com/google-research/honeyval/blob/86272d8d1fb4b3090037561cc31b28dc8a8350f8/src/http_apps/base_http_app.py>
- <https://github.com/google-research/honeyval/blob/86272d8d1fb4b3090037561cc31b28dc8a8350f8/src/tasks/agent_vs_http_app.py>

### Adaptive-environment and template inspiration

**[S10] PAIRED, primary author explanation and linked research.**

- <https://research.google/blog/paired-a-new-multi-agent-approach-for-adversarial-environment-generation/>

**[S11] ACCEL, author project and paper.**

- <https://accelagent.github.io/>
- <https://proceedings.mlr.press/v162/parker-holder22a.html>
- <https://github.com/facebookresearch/dcd>

**[S12] CAGE Challenge 4, official environment and deployment actions.**

- <https://cage-challenge.github.io/cage-challenge-4/pages/>
- <https://github.com/cage-challenge/cage-challenge-4>

**[S13] Honeypatch template tooling.**

- <https://github.com/dynatrace-oss/honeyquest/blob/main/docs/HONEYPATCH.md>
- <https://github.com/dynatrace-oss/honeyquest>

### Interface, renderer and containment

**[S14] Gymnasium environment API.**

- <https://gymnasium.farama.org/api/env/>

**[S15] PixiJS official documentation.**

- <https://pixijs.com/8.x/guides/getting-started/intro>

**[S16] AISI containment engineering.**

- <https://www.aisi.gov.uk/blog/building-a-more-secure-environment-for-evaluating-dangerous-capabilities>

### AgentEnv sources added in v0.3

**[S17] AgentEnv pinned source and package metadata.** Framework `0.9.1375`, protocol `0.1.390`; source inspection only.

- <https://github.com/scaleapi/agentenv-framework/tree/666c26a586c9118599352c7caa52f53d2e89fb62>
- <https://github.com/scaleapi/agentenv-framework/blob/666c26a586c9118599352c7caa52f53d2e89fb62/pyproject.toml>
- <https://github.com/scaleapi/agentenv-framework/blob/666c26a586c9118599352c7caa52f53d2e89fb62/packages/agentenv-protocol/pyproject.toml>

**[S18] Protocol SDK and deployment topology.**

- <https://github.com/scaleapi/agentenv-framework/blob/666c26a586c9118599352c7caa52f53d2e89fb62/packages/agentenv-protocol/README.md>
- <https://www.agentenvframework.com/docs/environments/topology>

**[S19] Local sandbox, roles, and trigger limits.**

- <https://github.com/scaleapi/agentenv-framework/blob/666c26a586c9118599352c7caa52f53d2e89fb62/src/agent_env/providers/sandbox_providers/local_sandbox.py>
- <https://www.agentenvframework.com/docs/sandboxes>
- <https://www.agentenvframework.com/docs/environments/rbac>
- <https://www.agentenvframework.com/docs/environments/triggers>

**[S20] Task episodes and the existing OpenEnv adapter.**

- <https://github.com/scaleapi/agentenv-framework/blob/666c26a586c9118599352c7caa52f53d2e89fb62/src/agent_env/task/episode/spec.py>
- <https://github.com/scaleapi/agentenv-framework/blob/666c26a586c9118599352c7caa52f53d2e89fb62/src/agent_env/openenv/environment.py>
- <https://www.agentenvframework.com/docs/tasks>

### Review limitations

The review checked the planning documents, relevant papers/documentation, and selected pinned code paths. It was not a complete upstream audit, a novelty proof, or an integration test. APIs, images, providers, and models must be validated during implementation. Preserve original notices for reused code/test assets and track patches. Research-specific source interpretations and corrections are in [RESEARCH_FINDINGS.md](RESEARCH_FINDINGS.md).
