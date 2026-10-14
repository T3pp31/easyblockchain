FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

COPY --from=ghcr.io/astral-sh/uv:0.11.17@sha256:03bdc89bb9798628846e60c3a9ad19006c8c3c724ccd2985a33145c039a0577b /uv /usr/local/bin/uv

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
