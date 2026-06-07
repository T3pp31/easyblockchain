# Operations Guide

This document describes logging, health checks, metrics, deployment, and release procedures for easyblockchain v2.1.

## Configuration

Configuration files live under `config/`:

| File | Purpose |
|------|---------|
| `default.yaml` | Local development defaults |
| `production.yaml` | Production template (TLS enabled) |
| `docker.yaml` | Container demo without TLS |

Override the config path with:

```bash
export EASYBLOCKCHAIN_CONFIG=/path/to/config.yaml
```

Or pass `--config` to the node CLI.

## Logging

Log level is controlled by `node.log_level`.

Structured JSON logging is enabled with:

```yaml
observability:
  log_format: "json"
```

JSON fields:

| Field | Description |
|-------|-------------|
| `timestamp` | UTC ISO-8601 timestamp |
| `level` | Log level |
| `logger` | Logger name |
| `message` | Log message |
| `node_id` | Node identifier (when available) |
| `peer_id` | Peer identifier (when present on record) |
| `block_index` | Block index (when present on record) |

Initialize logging via `useful_blockchain.observability.logging_config.configure_logging`.

## Health Checks

When `observability.enabled` is `true`, the node exposes HTTP endpoints on `observability.port` (default `9090`):

| Endpoint | Purpose | Success |
|----------|---------|---------|
| `GET /healthz` | Liveness | `200 {"status":"ok"}` |
| `GET /readyz` | Readiness | `200` when P2P is started and persistence is loaded |
| `GET /metrics` | Prometheus metrics | `200` when `prometheus-client` is installed |

Readiness also checks `observability.min_peers_for_ready` when set above zero.

## Metrics

Install observability extras:

```bash
uv sync --extra observability
```

Exported metrics:

| Metric | Type | Description |
|--------|------|-------------|
| `ebc_chain_height` | Gauge | Current chain height |
| `ebc_peer_count` | Gauge | Connected peer count |
| `ebc_blocks_accepted_total` | Counter | Accepted blocks |
| `ebc_sync_operations_total` | Counter | Chain sync operations |
| `ebc_pong_timeouts_total` | Counter | PONG timeouts |

Example Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: easyblockchain
    static_configs:
      - targets: ["node-host:9090"]
```

## Running the Node

After installation:

```bash
uv run easyblockchain-node --consensus pow --port 8765
```

Or:

```bash
uv run python examples/run_node.py --consensus pow --port 8765
```

## Docker

Build and run a 3-node network:

```bash
docker compose up --build
```

Health check:

```bash
curl -f http://localhost:9090/healthz
```

For TLS production deployments, mount certificates and use `config/production.yaml`:

```bash
docker run -v /data:/data -v /certs:/certs easyblockchain:latest \
  --config /app/config/production.yaml
```

## Kubernetes

Example manifests are in `deploy/kubernetes/node-deployment.yaml`.

Apply:

```bash
kubectl apply -f deploy/kubernetes/node-deployment.yaml
```

Probes target `/healthz` and `/readyz` on port `9090`.

## PyPI Release (GitHub Actions)

### Prerequisites

1. Add repository secret `PYPI_API_TOKEN` (PyPI API token with upload scope).
2. Ensure `main` allows GitHub Actions to push (Settings → Actions → General → Workflow permissions).

### Automated release (recommended)

1. Open **Actions → Release → Run workflow**.
2. Choose bump type: `patch`, `minor`, or `major`.
3. The workflow will:
   - bump `pyproject.toml`, `useful_blockchain/__init__.py`, and `setup.py`
   - commit to `main`, create tag `vX.Y.Z`, and publish a GitHub Release
4. `publish.yml` runs on release and uploads to PyPI using `PYPI_API_TOKEN`.

### Manual publish

- Run **Actions → Publish to PyPI → Run workflow** after a version bump is already on `main`.
- Or create a GitHub Release manually; publish runs on `release: published`.

## Production Notes

- PoW/PoS/P2P are educational implementations. Perform additional security review before production use.
- Enable TLS in `production.yaml` and mount valid certificates.
- Persist `node.data_dir` on durable storage.
- Prefer JSON logs and Prometheus metrics for operations visibility.
