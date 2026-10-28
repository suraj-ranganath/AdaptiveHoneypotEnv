# Research findings

Synthesis of the background research that informs [`DESIGN.md`](DESIGN.md). Written 2026-10-28 from a review of the sources named in the implementation handoff plus a survey of concurrent work. Where a claim is a vendor study, a figure read off a table, or otherwise uncertain, it is marked.

## 1. Where this sits relative to prior work

The specific combination we build — a **defender that creates real-backed decoy credentials mid-episode in response to observed attacker tool calls**, tested against an agent **swarm**, in an **RL-ready** environment — does not appear in prior or concurrent work we could find. The pieces exist separately:

- **AgentTrap** (arXiv 2610.02869, Oct 2026) is the closest adaptive analogue. An LLM controller generates stateful decoy *responses* grounded in the real app, escalating only after the agent commits to the decoy path. It decides responses rather than planting discoverable artifacts, and runs against a single SQL-injection target. Attack success fell from ~96% to ~79%; in ~19% of runs the agent handed over its own API key; several frontier harnesses (Claude Code, PentestGPT, AIDA) refused the credential request.
- **Tracebit** (agentic.tracebit.com, 2026) already reports, as a headline, that a canary fires **before genuine compromise** — in their AWS range, ~96% of runs that reached admin tripped a canary first, with a median ~8-minute lead. **We must not claim "warning before compromise" as a novel metric.** Our contribution is a *stricter, verified* form: engagement proven through the real backend, lead time measured per episode, against an adaptive placer.
- **Honeyval** (ICML 2026) evaluates attacking agents against honeypots, but its honeypot is a whole LLM-faked backend chosen once per run. It has **no** defender-side creation or adaptivity; its seeded `admin` account is a verification fixture, not a planted honeytoken.
- **CAGE Challenge 4 / CybORG** has a defender `DeployDecoy` action, but decoys are simulated process entries and exploits against them fail by rule — not measured deception against a real model.
- RL / game-theoretic decoy placement exists only against **scripted** attackers (attack-graph or CVE-replay), never learned against LLM agents.

**Framing takeaway:** lead with the adaptive, real-backed, swarm-facing, RL-ready combination. Present the protection metric as a verified refinement of Tracebit's, not as new.

## 2. What bait LLM agents actually take

From Honeyquest (RAID 2024, human study of 3,669 answers), its LLM follow-up (arXiv 2606.21037), CHeaT (USENIX Sec '25), and the Horizon3 LLM study:

- **Credential / key bait has the highest take rate** and is engaged fastest. In the human study, `private-key.pem`, `backup.tar.gz`, `keys.json`, and a dev-token JWT header all drew majority exploit attempts. LLMs take credential bait even more readily than humans (reported 83–100% for key/credential artifacts).
- **Obviousness is a curve.** Names containing "backup", "config", "k8s" drew *few* trap-flags; names containing "key" or "password" drew more; `passwords.txt` was the only decoy flagged as a trap more often than exploited. Target the middle: a plausible real misconfiguration, never anything with "honey"/"decoy"/"trap" or a too-good name.
- **Decoys must imitate real risks.** Real risky items (an `.ssh` dir, `.bash_history`) drew far more engagement than any decoy; the best decoys look like those.
- **Suspecting is not avoiding.** LLMs interacted with a decoy ~73% of the time *even after naming it a trap in their reasoning*. **Score behaviour (did they use the credential), never what the attacker says.**
- **Prompt-injection wording backfires.** Wrapping bait in injection text lowered take rate (CHeaT), roughly doubled detection (Honeyval), and triggered refusals (AgentTrap). Our bait is inert data, never an instruction.
- **Distraction is measurable and counterfactual.** Honeyquest's within-subject design (same case with vs without the decoy) showed adding a decoy lowered the rate of finding the real vulnerability by ~22% on average. This is the template for our headline metric.

## 3. How to make decoys credible (anti-fingerprinting)

Honeyquest's own dataset leaks fingerprints we must avoid: one JWT reused across 7 cases, identical file metadata ("9.7K Jun 6 2022") across decoys, a world-readable `private-key.pem`. Rules:

- Randomize every literal per episode — tokens, account names, sizes, timestamps, permissions — but keep them **internally consistent** (the credential in a runbook must match the account the compiler actually created).
- Real files must **reference** the decoy artifact; an orphan file nothing points to is a tell.
- Credentials for canary accounts must be shaped so they cannot work anywhere but the local service (no real-looking cloud key formats that a tool like TruffleHog could fingerprint offline).
- Mid-episode creation is itself a tell (fresh mtimes, no git history). Provisioning may happen eagerly, but committed artifacts must not expose creation timing, and naming/numbering must not separate decoy from genuine.

## 4. Verification and scoring (what to borrow)

- **ExploitGym** verifies success cryptographically: the secret is an HMAC-derived flag the agent cannot forge, checked against local ground truth after teardown — *claims of success are ignored*. It adds a second-stage judge asking whether the intended path was **causally necessary**, filtering shortcut successes. We adopt both: a crypto flag for genuine compromise, and (optionally) a judge asking whether a **decoy credential was causally necessary** to a catch.
- **Honeyval** uses a self-verifying marker — a hash of the first log line written server-side on success — so logs cannot accidentally contain the success token. We use the same pattern for decoy-engagement detection at the service boundary.
- **Anchor the defender reward to "was the real secret protected", measured against a no-decoy run of the same seed.** Rewarding "decoy touched" alone teaches the defender to spam decoys (CAGE-4 has *no* decoy reward term for exactly this reason). Keep a small per-decoy cost so placement stays deliberate.
- **Refusals are their own bucket.** Tracebit excluded 301/951 runs for refusals; telling an attacker deception may exist cut compromise sharply. Never score a refusal as a defender win, and always run a deception-aware attacker condition as a validity control.

## 5. Containment on Docker (and its limits)

From the AISI containment post, mapped to Docker (the mapping is ours):

- **The controller makes all LLM calls; sandboxes get no outbound.** This is the single most important control and it also makes the system portable — target/attacker containers need no network except an internal one.
- Put the target on an `internal` Docker network, publish no ports, drop all capabilities, `no-new-privileges`, read-only rootfs + tmpfs, non-root user, pid/mem/cpu limits, **never mount the docker socket**, mount fixtures read-only.
- Enforce isolation at the network/tool chokepoint, not via agent config flags (anything inside a container can bypass a CLI flag).
- Add pre-run self-tests: DNS, external TCP, and `host.docker.internal` must all **fail** from inside the sandbox.

**Limits to state honestly:** Docker shares one host kernel (no per-sandbox VM); gVisor/Kata are not available in Docker Desktop's VM; there is no cloud-security-group layer on a laptop. Our threat model is sound because attackers only ever hold our structured tools (no shell, no arbitrary URLs), but we document the kernel-sharing caveat rather than overclaiming VM-grade isolation.

## 6. Interface facts (Gymnasium)

- `terminated` = the task reached a terminal state (genuine compromise, all attackers done, resource horizon). `truncated` = an external cutoff (wall-clock, token cap). A budget that is *inherent* to the task counts as termination, and the remaining budget must then be in the observation. Infra-invalid runs are flagged in `info` and excluded, never bootstrapped.
- Use a flat `Discrete` over valid `(template, slot, context)` triples plus `wait`, with the mask in `info["action_mask"]`; a per-dimension `MultiDiscrete`/`Dict` mask cannot forbid invalid *combinations*. The free-text description is a separate `Text(240)`.
- Keep evaluation-only ground truth (decoy spans, flag value, attacker reasoning) in `info`, never in the observation returned to a policy.

## 7. Validity risks to design against

- Attackers that know deception exists avoid obvious decoys → run naive **and** deception-aware conditions.
- Over-eager agents make "caught" trivially easy (they exploit ~93% of even neutral lines) → always report against a **random-placement** baseline and a **no-decoy** control.
- Published canary/token formats are in training data → randomize and avoid known formats.
- Swarm cross-checking: if per-agent tokens are inconsistent, agents comparing notes can spot them → keep decoy facts internally consistent across what the swarm can see.
- Small samples and harness effects dominate this literature → fix a single shared attacker harness, log everything, size samples from a variance pilot, report CIs.

## Sources

ExploitGym (arXiv 2605.11086; repo `sunblaze-ucb/exploitgym@a8029e4`). Honeyval (arXiv 2605.29963; repo `google-research/honeyval@86272d8`). Honeyquest (arXiv 2408.10796; repo `dynatrace-oss/honeyquest`) and its LLM follow-up (arXiv 2606.21037). CAGE Challenge 4 / CybORG. PAIRED (arXiv 2012.02096), ACCEL (ICML 2022). AISI containment blog. Gymnasium API docs. Concurrent agent-deception work: AgentTrap (2610.02869), Tracebit (agentic.tracebit.com), Palisade LLM Agent Honeypot (2410.13919), Mantis (2410.20911), CHeaT (USENIX Sec '25), Rouxii (2609.26555), Thinkst. Incident context: METR/OpenAI–Hugging Face reports, Railway and OpenCode coverage (none of which attribute detection to honeytokens).
