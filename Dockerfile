FROM python:3.14-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src/ src/

RUN uv sync --frozen

COPY templates/ templates/
COPY patterns.yml patterns.yml
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 5001

ENTRYPOINT ["/app/entrypoint.sh"]
