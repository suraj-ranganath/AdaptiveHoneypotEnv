# Target image pins

Base image, linux/amd64 manifest digested and pulled for the gate A tests:

```text
python:3.12-slim@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b
```

Multi-arch index digest for the same tag, not used in the Dockerfile (the Dockerfile pins the amd64 manifest that was tested):

```text
sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
```

Python packages are the hashed lock in `requirements.txt`. Direct pins:

| Package | Version |
|---|---|
| fastapi | 0.115.12 |
| uvicorn | 0.34.2 |
| cryptography | 44.0.2 |
| passlib | 1.7.4 |
| bcrypt | 4.0.1 |
| python-jose | 3.4.0 |
| email-validator | 2.2.0 |
| pydantic | 2.10.6 |

The bridge image uses the same base digest and the Python standard library only.
