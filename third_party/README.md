# Third-party sources

Reviewed pins, also recorded in DESIGN.md §9.3:

- Honeyval `86272d8d1fb4b3090037561cc31b28dc8a8350f8` — vendored below
- AgentEnv `666c26a586c9118599352c7caa52f53d2e89fb62` (framework `0.9.1375`, protocol `0.1.390`) — reference only, not vendored
- ExploitGym `a8029e47135a29f1c1a6e79109bf86fba379b3f3` — architectural reference, not a runtime dependency
- [SwarmChat](https://github.com/Pranjal2041/swarmchat/tree/fb5aa6a05b40fba70f749cd3017aeb3219ab6ac1) `fb5aa6a05b40fba70f749cd3017aeb3219ab6ac1` (`0.1.0`, MIT) — optional runtime dependency, installed from the locked source; not vendored or modified. Its package includes the upstream license. The integration's use of the store and observer boundary is recorded in [docs/SWARMCHAT.md](../docs/SWARMCHAT.md).

`honeyval/` is the pinned SecretStorage `sec` app, its license, the upstream functional test, and the OpenAPI document. `honeyval/PATCHES.md` is the patch ledger. `app.py` is unmodified. The image entrypoint sets `email_validator.CHECK_DELIVERABILITY = False` before import; that is runtime configuration, recorded in the ledger, not a source patch.
