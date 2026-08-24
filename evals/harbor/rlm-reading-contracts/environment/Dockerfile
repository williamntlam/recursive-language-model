FROM python:3.12-slim

RUN useradd --create-home --shell /bin/bash agent

WORKDIR /workspace
COPY source /workspace/source
RUN chown -R root:root /workspace/source \
    && chmod -R a-w /workspace/source \
    && chown agent:agent /workspace

USER agent
