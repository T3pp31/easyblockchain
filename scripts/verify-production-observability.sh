#!/usr/bin/env bash
# Verify production-like observability: token injection and localhost health endpoints.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TOKEN="${EASYBLOCKCHAIN_OBSERVABILITY_TOKEN:-verify-script-token}"

find_free_port() {
  python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
}

DATA_DIR="$(mktemp -d)"
CONFIG_FILE="$(mktemp)"
CONTAINER_NAME="easyblockchain-obs-verify-$$"
USE_DOCKER=1
NODE_PID=""
RUN_IN_CONTAINER=0
# Ports are picked right before node startup (see prepare_ports_and_config);
# OBS_PORT/P2P_PORT may be overridden via the environment.
OBS_PORT="${OBS_PORT:-}"
P2P_PORT="${P2P_PORT:-}"

stop_node() {
  if [[ -n "$NODE_PID" ]]; then
    kill "$NODE_PID" >/dev/null 2>&1 || true
    wait "$NODE_PID" 2>/dev/null || true
    NODE_PID=""
  fi
  if [[ "$USE_DOCKER" -eq 1 ]]; then
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
}

cleanup() {
  stop_node
  rm -rf "$DATA_DIR" "$CONFIG_FILE"
}
trap cleanup EXIT

prepare_ports_and_config() {
  # data_dir to embed in the generated config (container path or host path)
  local data_dir="$1"
  # Pick ports right before node startup to shrink the TOCTOU window.
  OBS_PORT="${OBS_PORT:-$(find_free_port)}"
  P2P_PORT="${P2P_PORT:-$(find_free_port)}"
  cat >"$CONFIG_FILE" <<EOF
genesis:
  prev_hash: "0000000000000000000000000000000000000000000000000000000000000000"
consensus:
  type: pow
network:
  host: "0.0.0.0"
  port: ${P2P_PORT}
  bootstrap_peers: []
  tls:
    enabled: false
node:
  data_dir: "${data_dir}"
  log_level: "WARNING"
observability:
  enabled: true
  host: "127.0.0.1"
  port: ${OBS_PORT}
  log_format: "json"
  auth_enabled: true
EOF
}

run_python() {
  local code="$1"
  if [[ "$RUN_IN_CONTAINER" -eq 1 ]]; then
    docker exec "$CONTAINER_NAME" python -c "$code"
  else
    uv run python -c "$code"
  fi
}

run_checks() {
  echo "==> Checking endpoints"
  run_python "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:${OBS_PORT}/healthz', timeout=5).status)" \
    | awk '{print "OK   /healthz: HTTP", $1}'
  run_python "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:${OBS_PORT}/readyz', timeout=5).status)" \
    | awk '{print "OK   /readyz: HTTP", $1}'
  run_python "import urllib.error, urllib.request, sys
try:
  urllib.request.urlopen('http://127.0.0.1:${OBS_PORT}/metrics', timeout=5)
except urllib.error.HTTPError as e:
  if e.code != 401:
    print('FAIL: /metrics (no auth) returned', e.code, file=sys.stderr)
    sys.exit(1)
except urllib.error.URLError as e:
  print('FAIL: /metrics (no auth) unreachable:', e, file=sys.stderr)
  sys.exit(1)
else:
  print('FAIL: /metrics (no auth) returned 200', file=sys.stderr)
  sys.exit(1)"
  echo "OK   /metrics (no auth): HTTP 401"
  run_python "import urllib.request
req = urllib.request.Request('http://127.0.0.1:${OBS_PORT}/metrics', headers={'Authorization': 'Bearer ${TOKEN}'})
print(urllib.request.urlopen(req, timeout=5).status)" \
    | awk '{print "OK   /metrics (Bearer): HTTP", $1}'
}

wait_for_health() {
  local attempts=30
  local i
  for ((i = 1; i <= attempts; i++)); do
    if run_python "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${OBS_PORT}/healthz', timeout=2)" \
      >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "FAIL: node did not become healthy on 127.0.0.1:${OBS_PORT}"
  return 1
}

start_in_container() {
  echo "==> Starting container with EASYBLOCKCHAIN_OBSERVABILITY_TOKEN"
  prepare_ports_and_config "/data"
  docker run -d --name "$CONTAINER_NAME" \
    -e EASYBLOCKCHAIN_OBSERVABILITY_TOKEN="$TOKEN" \
    -v "$CONFIG_FILE:/config/production.yaml:ro" \
    -v "$DATA_DIR:/data" \
    easyblockchain:obs-verify \
    --config /config/production.yaml
  RUN_IN_CONTAINER=1
}

start_with_uv() {
  USE_DOCKER=0
  RUN_IN_CONTAINER=0
  echo "==> Running node with uv (EASYBLOCKCHAIN_OBSERVABILITY_TOKEN set)"
  export EASYBLOCKCHAIN_OBSERVABILITY_TOKEN="$TOKEN"
  prepare_ports_and_config "$DATA_DIR"
  uv run python -m useful_blockchain.cli --config "$CONFIG_FILE" &
  NODE_PID=$!
}

# Launch the node and wait for health; on failure retry once with fresh ports
# to recover from TOCTOU races on the ephemeral ports.
start_and_verify() {
  local start_fn="$1"
  if launch_and_wait "$start_fn"; then
    run_checks
    return 0
  fi
  echo "==> Node failed to become healthy; retrying once with fresh ports"
  stop_node
  OBS_PORT=""
  P2P_PORT=""
  if launch_and_wait "$start_fn"; then
    run_checks
    return 0
  fi
  return 1
}

launch_and_wait() {
  "$1"
  wait_for_health
}

echo "==> Verifying production observability (token + localhost probes)"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "==> Building Docker image"
  if docker build -t easyblockchain:obs-verify "$ROOT_DIR"; then
    start_and_verify start_in_container || { echo "FAIL: observability verification failed"; exit 1; }
  else
    echo "==> Docker build failed; falling back to uv run"
    start_and_verify start_with_uv || { echo "FAIL: observability verification failed"; exit 1; }
  fi
else
  echo "==> Docker not available; falling back to uv run"
  start_and_verify start_with_uv || { echo "FAIL: observability verification failed"; exit 1; }
fi

echo "==> All production observability checks passed"
