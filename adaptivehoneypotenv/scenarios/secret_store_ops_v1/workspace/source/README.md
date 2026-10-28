# SecretStorage source

Pinned public source: google-research/honeyval `86272d8d1fb4b3090037561cc31b28dc8a8350f8`

Path in that tree: `data/baxbench-webapps/SecretStorage/sec`

WS1 vendors that directory at `third_party/honeyval/data/baxbench-webapps/SecretStorage/sec`. `materialize_workspace` copies `app.py` into this folder. The application is Apache-2.0, Copyright 2026 Google LLC. The bytes are unmodified; see `third_party/honeyval/PATCHES.md`.

Workflow procedures log in with the account email and password. The service returns a token. The stored value is read with `GET /get_secret` for that account's username. Request fields are in the mounted application source.
