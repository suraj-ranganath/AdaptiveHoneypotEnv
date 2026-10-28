# linux/amd64 manifest tested for gate A. See PINS.md.
FROM python:3.12-slim@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    PYTHONPATH=/opt/secretstorage

RUN groupadd --gid 65532 app \
    && useradd --uid 65532 --gid 65532 --home-dir /home/app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /opt/secretstorage /run/state \
    && chown 65532:65532 /run/state

COPY docker/target/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt \
    && python -c "from passlib.context import CryptContext; ctx = CryptContext(schemes=['bcrypt'], deprecated='auto'); hashed = ctx.hash('login-proof'); assert ctx.verify('login-proof', hashed); assert not ctx.verify('other-password', hashed); print('passlib-bcrypt login proof ok')"

COPY third_party/honeyval/data/baxbench-webapps/SecretStorage/sec/app.py /opt/secretstorage/app.py
COPY docker/target/entrypoint.py /opt/secretstorage/entrypoint.py
COPY docker/target/maintenance.py /opt/secretstorage/maintenance.py
RUN chmod 0444 /opt/secretstorage/app.py /opt/secretstorage/entrypoint.py /opt/secretstorage/maintenance.py \
    && chown -R root:root /opt/secretstorage

USER 65532:65532
WORKDIR /run/state
ENTRYPOINT ["python", "/opt/secretstorage/entrypoint.py"]
