FROM python:3.9-slim-buster

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get -y install git curl jq && apt-get clean && rm -rf /var/cache/apk/*

COPY ./nx_source_file_compliance ./nx_source_file_compliance
COPY ./nx_lint ./nx_lint
RUN pip3 install ./nx_source_file_compliance/ ./nx_lint/

ARG APP_UID=1000
ARG APP_GID=1000

WORKDIR /workdir
RUN addgroup --gid $APP_GID user && \
    adduser --uid $APP_UID --disabled-password --ingroup user user && \
    install -d /workdir/ -o $APP_UID -g $APP_GID

USER user

COPY ./scripts/open_source_check/open_source_check.py \
    ./scripts/open_source_check/no_checkable_open_source_files_check.py \
    ./scripts/open_source_check/open_source_check_config.json \
    /workdir/

ENTRYPOINT ["/bin/bash", "-c"]
