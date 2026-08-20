FROM python:3.12-slim

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin rlm \
    && mkdir -p /opt/rlm/rlm/core /opt/rlm/rlm/domains /repl \
    && chown rlm:rlm /repl

COPY rlm/ipc.py rlm/repl_ns.py rlm/errors.py /opt/rlm/rlm/
COPY rlm/core/types.py rlm/core/history.py /opt/rlm/rlm/core/
COPY rlm/domains/repo.py rlm/domains/corpus.py /opt/rlm/rlm/domains/
COPY docker/repl_server.py /opt/rlm/repl_server.py

RUN printf '%s\n' '' > /opt/rlm/rlm/__init__.py \
    && printf '%s\n' '' > /opt/rlm/rlm/core/__init__.py \
    && printf '%s\n' '' > /opt/rlm/rlm/domains/__init__.py

ENV PYTHONPATH=/opt/rlm
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER rlm
WORKDIR /repl
CMD ["python", "-u", "/opt/rlm/repl_server.py"]
