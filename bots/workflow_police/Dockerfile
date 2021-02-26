FROM python:3.8-slim-buster

ARG GIT_COMMIT=unknown
ENV BOT_REVISION=$GIT_COMMIT
ENV BOT_NAME=Police

RUN apt-get update && apt-get -y install curl && apt-get clean
# Use tini as a subreaper in Docker container to adopt zombie processes.
ARG TINI_VERSION=v0.19.0
RUN curl --fail --silent --show-error --location --output /sbin/tini \
  https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini-static-$(dpkg --print-architecture) \
  && chmod +x /sbin/tini

COPY ./bots/workflow_police/requirements.txt .
RUN pip3 install -r requirements.txt

ARG APP_UID=1000
ARG APP_GID=1000

WORKDIR /workdir
RUN addgroup --gid $APP_GID workflow-police && \
    adduser --uid $APP_UID --disabled-password --ingroup workflow-police workflow-police --gecos "nx police" && \
    install -d /workdir/ -o $APP_UID -g $APP_GID

USER workflow-police

COPY ./bots/workflow_police/. /workdir/
COPY ./automation_tools/. /workdir/automation_tools

ENTRYPOINT ["/sbin/tini", "--", "/workdir/police.app"]
