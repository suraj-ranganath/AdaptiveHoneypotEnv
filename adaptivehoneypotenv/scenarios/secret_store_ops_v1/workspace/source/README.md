# SecretStorage source

Pinned public source: google-research/honeyval `86272d8d1fb4b3090037561cc31b28dc8a8350f8`

Path in that tree: `data/baxbench-webapps/SecretStorage/sec`

The lab controller mounts that directory here from `third_party/honeyval` when the vendor tree is present. The application is Apache-2.0, Copyright 2026 Google LLC.

Workflow procedures log in with the account email and password. The service returns a token. The stored value is read with `GET /get_secret` for that account's username. Request fields are in the mounted application source.
