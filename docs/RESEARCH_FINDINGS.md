# Research findings

**Reviewed:** 2026-10-28. Evidence supporting [DESIGN.md](DESIGN.md) v1.1; this is a focused source review, not an exhaustive systematic review or novelty proof. Numerical findings below belong to their original experimental settings, not predictions for our environment. The handoff retains source entry points S1–S20.

## 1. Research question and prior work

Our proposed contribution is an environment where a defender creates discoverable credential artifacts backed by real accounts during an episode, conditioned on observed activity, and is evaluated against scheduled attacker teams through a reusable learning interface. The reviewed sources motivate this combination, but do not prove no prior system has explored it. Avoid absolute claims such as “RL placement has never been tested against LLM agents.”

- **AgentTrap** uses stateful response deception against autonomous penetration-testing agents. Its reported real-target success rate changes from 95.8% to 79.2% in its setting. This supports studying adaptive deception, but its intervention is response-based and includes mechanisms outside our inert-artifact scope. [Paper](https://arxiv.org/html/2610.02869v1).
- **Tracebit** studies actual canaries in an AWS range. It reports early warning in 95.9% of canary-present runs reaching admin, with a median eight-minute gap. Canary presence alone did not significantly reduce full compromise; disclosure changed outcomes. Thus neither real-backed canaries nor warning-before-compromise is novel by itself, and detection must remain distinct from prevention. This is a vendor study with exclusions and a different harness. [Specific study](https://agentic.tracebit.com/ai-agents-canaries/).
- **Honeyval** evaluates HTTP honeypot backends and uses separate attacker-capability and functionality controls. Its generated honeypot responses can depend on interaction history; that is different from our defender creating and placing workspace artifacts. We reuse a real app rather than its LLM-emulated backend. [Project](https://honeyval.xyz/), [paper](https://arxiv.org/html/2605.29963v1).
- **CAGE Challenge 4 / CybORG** provides constrained defender deployment actions. Its rules alert the defender and automatically fail an exploit against a decoy. We must measure actual tool interactions instead. Do not attribute a particular reward-design rationale to CAGE without evidence. [Official challenge description](https://cage-challenge.github.io/cage-challenge-4/pages/).
- **PAIRED and ACCEL** motivate constrained environment construction and structured changes. They do not establish that our reward, task, or learning process will succeed. We borrow the need to preserve task validity, not their regret objective or theoretical guarantees. [PAIRED](https://research.google/blog/paired-a-new-multi-agent-approach-for-adversarial-environment-generation/), [ACCEL](https://proceedings.mlr.press/v162/parker-holder22a.html).

## 2. Enticement does not establish distraction

The human **Honeyquest** study uses code-based questionnaires. Its paired cases found a reduction in real-risk selection with added deception. This motivates matched comparisons, but a questionnaire choice is not successful credential use in a running application. [Human study](https://arxiv.org/html/2408.10796).

The **Honeyquest for LLMs** follow-up, authored by Horizon3.ai researchers, is the same study previously described separately as the “Horizon3 LLM study.” Its latest reviewed version explicitly reports that the aggregate human diversion effect did not carry over to its LLM cohort. It also reports that recognizing a trap does not reliably prevent exploit-marking. These are reasons to score behavior and test protection separately, not evidence that bait necessarily prevents compromise. [LLM study, v3](https://arxiv.org/html/2606.21037v3).

Credential artifacts are a reasonable starting hypothesis, supported by these studies' results. The exact names, take rates, and artifact rankings should not be generalized into probabilities for our tool-using swarm. Our real app makes the use of a credential independently verifiable.

**Implication for this project:** detection-first outcomes match the original goal and user decision. Keep compromise reduction, warning lead time, added attacker effort, and benign disruption distinct. Use a no-decoy control to assess capability and protection; use the later matched initial-placement ablation to assess adaptation.

## 3. Attacker awareness and prompt injection

**Rouxii** evaluates deception-aware attackers and reports substantial changes in honeypot identification under matched prompting. This supports a deception-aware condition and anti-fingerprinting checks; our short warning prompt is not equivalent to its complete counter-deception system. [Paper](https://arxiv.org/html/2609.26555v1).

**CHeaT** studies multiple techniques; adding injection framing generally reduced its defense success rate, with some exceptions. **Mantis** reports effective injection-based defenses in its own setting. The literature therefore does not support a universal “prompt injection backfires” rule. Our inert-data constraint is an experimental scope choice that separates template credibility from instruction-following manipulation. [CHeaT](https://www.usenix.org/system/files/usenixsecurity25-ayzenshteyn.pdf), [Mantis](https://arxiv.org/html/2410.20911v2).

**Palisade's LLM Agent Honeypot** uses SSH honeypots, injection, and timing signals to identify possible AI attackers in the wild. Its observational detections differ from verified account use in our controlled experiment. **Thinkst** demonstrates established canary/tripwire infrastructure; we do not claim to invent honeytokens. [Palisade](https://arxiv.org/html/2410.13919v2), [Thinkst overview](https://help.canary.tools/hc/en-gb/articles/4701687447325-What-are-Canarytokens).

## 4. Credibility and validity risks

These are our design implications, not experimentally established rules for this scenario:

- Give attackers a workflow objective, with account identity inferred from coherent evidence. Naming the exact unique target account makes other-account credentials easy to dismiss.
- Use the same visible account, password, and value formats for true and decoy assets. Randomize plausible literals consistently; do not randomize permissions or timestamps in ways that break the scenario.
- Discoverability comes from actual directory listings, search, and internal references. An incoming reference from a pre-existing file is not mandatory for every deployment. The runbook template has a companion reference without editing the genuine route.
- Mid-episode file appearance can be noticed even if timestamps are absent. Do not claim perfect concealment or retroactively alter tool observations. Measure this limitation with deception-aware agents.
- Inspect search ranking, clipping, route length, and the first six-attempt window. If a capable attacker routinely finishes before the second defender decision, the fixture does not meaningfully test adaptation.
- A scheduled trio on a shared budget tests a bounded coordination setting. It cannot establish results for large concurrent swarms.

Honeypatch is a useful declarative-text reference, but its own documentation labels it a proof of concept. It does not provide our real-account compiler transaction. [Honeypatch documentation](https://github.com/dynatrace-oss/honeyquest/blob/main/docs/HONEYPATCH.md).

## 5. Verification and implementation evidence

ExploitGym's protocol combines flag verification with an intended-vulnerability judge. Its pinned implementation documents HMAC-based flags and separate controller secrets. We use private unpredictable values and explicit provenance, but do not adopt the vulnerability judge for primary canary scoring. [Paper](https://arxiv.org/html/2605.11086v1), [pinned operational documentation](https://github.com/sunblaze-ucb/exploitgym/blob/a8029e47135a29f1c1a6e79109bf86fba379b3f3/docs/eval.md).

Honeyval's callback code writes a marker derived from the first log line. This is provenance instrumentation, not cryptographic authentication of arbitrary untrusted logs. Our scorer instead verifies trusted invocation metadata and exact delivered values. [Callback implementation](https://github.com/google-research/honeyval/blob/86272d8d1fb4b3090037561cc31b28dc8a8350f8/src/callbacks/base.py).

The pinned SecretStorage app has registration/login/get/set operations, no account-deletion endpoint, a fallback APP_SECRET, and a process-generated salt. Its positive functional tests do not replace our negative cross-account tests. These facts require explicit configuration, fresh process/DB resets, and a private within-process DB rollback mechanism. [App](https://github.com/google-research/honeyval/blob/86272d8d1fb4b3090037561cc31b28dc8a8350f8/data/baxbench-webapps/SecretStorage/sec/app.py), [tests](https://github.com/google-research/honeyval/blob/86272d8d1fb4b3090037561cc31b28dc8a8350f8/third_party/baxbench/scenario_tests/secret_storage.py).

Keep refusals, infrastructure failures, and compromise as distinct recorded outcomes. Tracebit reports substantial refusal exclusions; its conditional rates should not be read as rates over every launched run. Our reporting retains all-run counts and flags, alongside explicitly defined valid/capable subsets.

## 6. AgentEnv fit and containment

The user approved **AgentEnv around a shared custom core**. Reviewed revision: `666c26a586c9118599352c7caa52f53d2e89fb62` (framework `0.9.1375`, protocol `0.1.390`). Its SDK, task graph, artifacts, and run integration are useful. Our compiler, scheduler, scoring, and event projection remain project-specific. [Protocol SDK](https://github.com/scaleapi/agentenv-framework/blob/666c26a586c9118599352c7caa52f53d2e89fb62/packages/agentenv-protocol/README.md), [tasks](https://www.agentenvframework.com/docs/tasks).

The inspected OpenEnv adapter steps through tools and computes episode scores; its reset does not forward the supplied seed. Local sandbox egress policies, trusted actor identity, six-attempt scheduling, and dense rewards therefore require explicit project contracts. Do not infer them from a framework's RL positioning. [Adapter source](https://github.com/scaleapi/agentenv-framework/blob/666c26a586c9118599352c7caa52f53d2e89fb62/src/agent_env/openenv/environment.py), [sandbox support](https://www.agentenvframework.com/docs/sandboxes), [role semantics](https://www.agentenvframework.com/docs/environments/rbac).

AISI describes layered outbound restrictions and validation after containment failures. Our host-controller/isolated-target/bridge design applies that motivation to structured tools; it still needs network and access tests. Docker is not a VM-grade security claim. Internal DNS needed for service discovery is distinct from external DNS forwarding/exfiltration. [AISI engineering report](https://www.aisi.gov.uk/blog/building-a-more-secure-environment-for-evaluating-dangerous-capabilities).

## 7. Interface and reproducibility

The Gymnasium distinction is task termination versus external truncation. Our declared attempt and generated-token budgets are inherent task state and terminate the episode when exhausted. External cost/wall cutoffs truncate. Invalid infrastructure runs are separately excluded from training rather than bootstrapped. [Gymnasium API](https://gymnasium.farama.org/api/env/).

A flat catalogue must enumerate valid **plans**, including two-item deployments and description variants, with stable indices and a dynamic mask. Separate dimension masks cannot by themselves express all pair/slot constraints. Contextual descriptions require structured actions; a `Text` space alone does not make discrete PPO applicable. These are project design decisions rather than prescribed Gymnasium behavior.

Store original delivered outputs and private fixture state. A layout seed is not enough to reproduce hosted model choices. Paired comparisons share initial fixtures, not a fabricated common post-intervention trajectory. PixiJS is a suitable 2D renderer for the observer; events, not animation, advance the experiment. [PixiJS documentation](https://pixijs.com/8.x/guides/getting-started/intro).

## 8. Motivation-source corrections and model availability

The README retains the original motivation and abstract while separating incident evidence from our threat model. METR reports around 700 agents participating in the Hugging Face attack and emphasizes collective efforts to understand/circumvent scoring. Railway's linked disclosure does not substantiate the previously quoted “1.85% / about 100,000” count or establish abliterated-model use. Those unsupported details were removed. The inaccessible NBC page was replaced with primary material. [METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/), [OpenAI reports](https://openai.com/hugging-face-incident-and-misalignment/), [Railway](https://blog.railway.com/p/security-disclosure-wednesday-october-21st).

The selected OpenRouter model is listed and advertises tool calling. That is availability evidence, not a refusal-free or capability guarantee. OpenCode Zen's model catalogue listed `glm-5.3-flash-free` on the review date; free availability and tool compatibility must be checked during implementation. Freeze actual provider routing and generation settings for research. [OpenRouter](https://openrouter.ai/z-ai/glm-5.3-flash), [Zen catalogue](https://opencode.ai/zen/v1/models).

## 9. What remains unvalidated

No environment was installed or executed in this review. Actual fixture credibility, attacker capability, adaptation opportunity, compiler rollback, networking, provider accounting, and UI usability remain build-gate work. Claims of improved defense require data; claims of generalization require held-out layouts and broader opponents/tasks. These limits do not prevent a useful, honest hackathon demo.
