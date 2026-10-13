FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE MANIFEST.in setup.py ./
COPY useful_blockchain ./useful_blockchain
COPY config ./config

RUN uv sync --frozen --no-dev --extra observability

# VOLUME 宣言より前に行う必要がある(VOLUME 後の変更は破棄されるため)
RUN mkdir -p /data && chown appuser:appuser /data

VOLUME ["/data"]
EXPOSE 8765 9090

USER appuser
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["easyblockchain-node"]
CMD ["--config", "/app/config/docker.yaml"]
