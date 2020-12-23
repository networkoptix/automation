FROM python:3.8-alpine

COPY ./bots/robocat/requirements.txt .
RUN apk add --no-cache tini gcc musl-dev libffi-dev openssl-dev git openssh-client && \
    pip3 install -r requirements.txt && \
    apk del gcc musl-dev libffi-dev openssl-dev

ARG APP_UID=1000
ARG APP_GID=1000

WORKDIR /workdir
RUN addgroup --gid $APP_GID workflow-robocat && \
    adduser --uid $APP_UID --disabled-password --ingroup workflow-robocat workflow-robocat && \
    install -d /workdir/ -o $APP_UID -g $APP_GID

USER workflow-robocat

COPY ./bots/robocat/. /workdir/
COPY ./automation_tools/. /workdir/automation_tools

ENTRYPOINT ["/sbin/tini", "--", "/workdir/robocat.app", "--config=/workdir/config.yaml"]
