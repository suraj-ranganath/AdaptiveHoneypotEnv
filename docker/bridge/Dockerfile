# Same tested amd64 base as the target. Standard library only.
FROM python:3.12-slim@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

RUN groupadd --gid 65532 app \
    && useradd --uid 65532 --gid 65532 --home-dir /home/app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /opt/bridge

COPY docker/bridge/bridge.py /opt/bridge/bridge.py
RUN chmod 0444 /opt/bridge/bridge.py && chown -R root:root /opt/bridge

USER 65532:65532
ENTRYPOINT ["python", "/opt/bridge/bridge.py"]
