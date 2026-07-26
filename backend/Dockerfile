FROM node:20-bookworm-slim AS node_runtime


FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# PythonMonkey (used by py-iztro) builds its JS runtime during installation.
# Copy the compact official Node runtime instead of installing Debian's full
# npm dependency tree. Build-only compilers and Node.js stay out of the final
# service image.
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node_runtime /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv

COPY requirements.runtime.txt ./requirements.runtime.txt
COPY requirements ./requirements

# py-iztro over-pins Pydantic 2.10.6 while LlamaIndex Workflows requires
# Pydantic >=2.11.5. Its runtime API is compatible, so keep the service's
# resolved Pydantic and install only this package without dependency rewrite.
RUN --mount=type=cache,target=/root/.cache/pip \
    /opt/venv/bin/pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        torch==2.5.0+cpu \
    && /opt/venv/bin/pip install \
        -c requirements/runtime-constraints.txt \
        -r requirements.runtime.txt \
    && /opt/venv/bin/pip install --no-deps py-iztro==0.1.5


FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY . ./

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
