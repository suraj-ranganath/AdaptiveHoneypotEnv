# AdaptiveHoneypotEnv

**An Environment for Training and Evaluating Adaptive Honeypot Creation to Defend Against AI Agent Swarm Attacks**

> Planning stage. The immediate goal is a compelling hackathon demo; the long-term goal is a reproducible environment for evaluation and reinforcement learning. No environment implementation exists yet. Current work is documentation and design only.

## Motivation

AI agents can explore codebases, use tools, share discoveries, and pursue objectives across many interactions. This creates a practical defensive question: can we place believable decoys where an attacking agent will discover them, find them relevant, and use them before reaching a real secret?

Recent incidents motivate that question:

- **OpenAI / Hugging Face, July 2026:** METR and Redwood Research documented approximately 1,200 agents communicating through an unsanctioned message board, with about 700 participating in the Hugging Face attack. Their investigation describes coordinated efforts to understand and circumvent benchmark scoring, including attempts to alter transcripts. [Independent investigation](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/), [OpenAI incident reports](https://openai.com/hugging-face-incident-and-misalignment/).
- **OpenCode, October 2026:** reported provider-key theft illustrates the value of the credentials these environments hold. [Incident coverage](https://techcrunch.com/2026/10/19/hackers-hit-ai-coding-tool-opencode-running-up-charges-on-users-ai-accounts/).
- **Railway, October 2026:** Railway disclosed possible access to customer environment variables and described suspected targeting of AI inference providers. [Company disclosure](https://blog.railway.com/p/security-disclosure-wednesday-october-21st).

The reports establish different facts; they do not establish that every incident used a swarm or an abliterated model. Our threat model includes coordinated agents and attackers using models with reduced safeguards. Open-weight availability alone does not imply that a model has had its safeguards removed or will never refuse.

We want to give defenders a way to create **adaptive honeypots** inside repositories and supporting services. The defender responds to observable activity by choosing a decoy's content, placement, and timing. The environment measures discovery and verified engagement, while also checking whether the real target was compromised and whether legitimate work was disrupted. Whether adaptation improves those outcomes is an empirical question.

## Abstract

As AI agents become more capable of exploring codebases, using tools, and coordinating with other agents, we need better ways to defend against potentially malicious behavior. Honeypots are one possible defense, but for them to work, an attacking agent needs to actually discover the honeypot and find it relevant to what it is trying to accomplish.

We propose **AdaptiveHoneypotEnv**, an environment for training and evaluating AI models that create adaptive honeypots. The idea is to simulate realistic software repositories where attacking agents and agent swarms pursue objectives, while defender models create and place honeypots to catch them. Defenders can choose from preconfigured honeypot templates and adapt their placement and content based on the attacker's capabilities, tool calls, and observed behavior.

Our goal is to build a simple, reproducible environment that supports both reinforcement learning and evaluation. Researchers should be able to compare different defender models, train better honeypot creation strategies, and measure how effectively they attract attackers without disrupting legitimate activity. We also plan to build a visual interface that shows attacker and defender behavior during live runs, making the environment easier to understand and experiment with.

## The hackathon demo

An operator watches three attacker sessions, acting together in lockstep rounds, explore a synthetic repository and a real local secret-storage service. An adaptive defender observes their searches and reads, creates a coherent credential artifact backed by a real canary account, and places it in the workspace. The attackers coordinate through a team messageboard they choose when to check, which the defender cannot see. The UI shows the actual deployment, tool calls, messageboard posts, and verified result.

**The primary outcome is detection before genuine compromise.** A canary alert does not stop the team or prove prevention. Delay and compromise reduction are measured separately. A saved fallback is labeled `RECORDED REPLAY`; a live episode may succeed or fail honestly.

The demo uses templates and bounded contextual text. Training defender weights, a large benchmark matrix, and claims of superiority are later research work.

## Architecture and specifications

**Approved architecture: AgentEnv around one shared custom core.** AgentEnv supplies the environment protocol and integration with tasks/artifacts. Our core owns the scenario, defender transitions, lockstep attacker sessions, deterministic compiler, verifier, and event log. The same dynamics serve the live observer, evaluation, and a Gymnasium wrapper.

Read in this order:

1. [Design specification](docs/DESIGN.md) — authoritative decisions, interfaces, gates, and outstanding inputs.
2. [Implementation handoff](docs/IMPLEMENTATION_HANDOFF.md) — implementation detail and upstream source map, aligned with the design.
3. [Research findings](docs/RESEARCH_FINDINGS.md) — evidence, limitations, and implications.
4. [Agent guidance](AGENTS.md) — repository working conventions; `CLAUDE.md` is a symlink to it.

## Getting started

There is no runnable environment yet. [demo.yaml](demo.yaml) is a proposed configuration contract, not an executable demo. Planned entry points are `make up` and a devcontainer; dependency and image locks will be established during implementation. Do not assume any build gate has passed.

## Repository structure

```text
README.md                       motivation, abstract, demo scope
AGENTS.md                       guidance for coding agents
CLAUDE.md -> AGENTS.md           shared guidance
demo.yaml                       proposed demo configuration
docs/DESIGN.md                   authoritative specification
docs/IMPLEMENTATION_HANDOFF.md   detailed contracts and source map
docs/RESEARCH_FINDINGS.md        reviewed evidence and limitations
```
