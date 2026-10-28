# Honeyval patch ledger

Pinned revision: `google-research/honeyval@86272d8d1fb4b3090037561cc31b28dc8a8350f8`

Source review is not integration testing. Hashes below are SHA-256 of the bytes committed in this tree. They match the bytes fetched from that revision.

| Path | SHA-256 | Local patch |
|---|---|---|
| `data/baxbench-webapps/SecretStorage/sec/app.py` | `7e51814c21fa091435ef8a552ca4c2063bdfd59d250407abf5e4b74556573d7a` | none |
| `data/baxbench-webapps/SecretStorage/sec/cwes.json` | `44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a` | none |
| `third_party/baxbench/scenario_tests/secret_storage.py` | `e8969ddcfb791bd109fd7ffd0bc3e13d31a6014ca1cc0ab6f5e9eb7a40bd40ba` | none |
| `third_party/baxbench/openapi_specifications/secret_storage.yaml` | `3e6cbe80daa1f3fc4fa0708c3672d9eb7e53acd32e37ab07ffb3e17814d3c164` | none |
| `LICENSE` (Apache-2.0, repository root) | `58d1e17ffe5109a7ae296caafcadfdbe6a7d176f0bc4ab01e12a689b0499d8bd` | none |
| `third_party/baxbench/LICENSE` (MIT) | `04f580a0fa6a36d612f78963ef6f59a336f93de30fd462a291448b3e8b07000c` | none |

## Runtime configuration, not a source patch

`docker/target/entrypoint.py` sets `email_validator.CHECK_DELIVERABILITY = False` before importing `app`. The upstream module reads that global when validating `EmailStr`. With the default left on, registration performs a DNS lookup. That lookup is both an egress channel and a failure mode here: containment blocks external DNS, and `example.com` publishes a NULL MX, so the upstream functional cases would never return 201. The application source is unchanged. The library documents this global as caller-settable.

The image entrypoint also refuses to start when `APP_SECRET` is missing, shorter than 32 characters, or equal to the insecure fallback literal in `app.py`. The fallback remains in the unmodified source and is never used by the launcher.

`DATABASE_FILE` stays `db.sqlite3`, resolved relative to the process working directory. The container working directory is the tmpfs at `/run/state`, so each episode's database is created there without patching the path constant.

## Dependency pin tested with this tree

`passlib==1.7.4` and `bcrypt==4.0.1`, locked with hashes in `docker/target/requirements.txt`. The image build hashes a password with the same `CryptContext(schemes=["bcrypt"])` the app uses and checks that verification succeeds. Episode tests repeat that proof through `POST /login`.
