"""本番相当 observability 設定の統合テスト。"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from http_helpers import http_get
from useful_blockchain.network.node import Node

TEST_TOKEN = "test-integration-token"


def _production_like_yaml(port: int, data_dir: Path) -> str:
    return f"""\
genesis:
  prev_hash: "0000000000000000000000000000000000000000000000000000000000000000"
consensus:
  type: pow
network:
  host: "127.0.0.1"
  port: 0
  bootstrap_peers: []
  tls:
    enabled: false
node:
  data_dir: "{data_dir}"
  log_level: "WARNING"
observability:
  enabled: true
  host: "127.0.0.1"
  port: {port}
  log_format: "json"
  auth_enabled: true
  health_path: "/healthz"
  ready_path: "/readyz"
  metrics_path: "/metrics"
  min_peers_for_ready: 0
"""


def _write_production_config(tmp_path: Path) -> tuple[Path, int]:
    port = _find_free_port()
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "production.yaml"
    config_path.write_text(_production_like_yaml(port, data_dir), encoding="utf-8")
    return config_path, port


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def production_config(tmp_path: Path) -> tuple[Path, int]:
    return _write_production_config(tmp_path)


@pytest.mark.integration
def test_node_fails_without_observability_token(
    monkeypatch: pytest.MonkeyPatch,
    production_config: tuple[Path, int],
) -> None:
    # Given: auth_enabled だが EASYBLOCKCHAIN_OBSERVABILITY_TOKEN が未設定
    # When: Node を初期化する
    # Then: ValueError が発生する
    config_path, _ = production_config
    monkeypatch.delenv("EASYBLOCKCHAIN_OBSERVABILITY_TOKEN", raising=False)
    with pytest.raises(ValueError, match="auth_enabled requires"):
        Node(config_path=config_path)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_node_starts_with_observability_token(
    monkeypatch: pytest.MonkeyPatch,
    production_config: tuple[Path, int],
) -> None:
    # Given: production 相当設定と EASYBLOCKCHAIN_OBSERVABILITY_TOKEN
    # When: Node を起動する
    # Then: 起動に成功する
    config_path, observability_port = production_config
    monkeypatch.setenv("EASYBLOCKCHAIN_OBSERVABILITY_TOKEN", TEST_TOKEN)
    node = Node(config_path=config_path)
    assert node.settings.observability.auth_token == TEST_TOKEN
    await node.start()
    try:
        assert node._health_server.actual_port == observability_port
    finally:
        await node.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_observability_endpoints_with_auth(
    monkeypatch: pytest.MonkeyPatch,
    production_config: tuple[Path, int],
) -> None:
    # Given: auth_enabled で起動済みの Node
    # When: healthz / readyz / metrics にアクセスする
    # Then: 期待するステータスコードが返る
    config_path, observability_port = production_config
    monkeypatch.setenv("EASYBLOCKCHAIN_OBSERVABILITY_TOKEN", TEST_TOKEN)
    node = Node(config_path=config_path)
    await node.start()
    try:
        status, body = await http_get("127.0.0.1", observability_port, "/healthz")
        assert status == 200
        assert json.loads(body.decode()) == {"status": "ok"}

        status, body = await http_get("127.0.0.1", observability_port, "/readyz")
        assert status == 200
        assert json.loads(body.decode()) == {"status": "ready"}

        status, _ = await http_get("127.0.0.1", observability_port, "/metrics")
        assert status == 401

        status, body = await http_get(
            "127.0.0.1",
            observability_port,
            "/metrics",
            authorization=f"Bearer {TEST_TOKEN}",
        )
        assert status == 200
        assert b"ebc_chain_height" in body
    finally:
        await node.stop()


@pytest.mark.integration
def _sync_http_status(host: str, port: int, path: str) -> int:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(f"http://{host}:{port}{path}")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def test_cli_starts_with_observability_token_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    production_config: tuple[Path, int],
) -> None:
    # Given: production 相当設定と CLI 起動用トークン
    # When: easyblockchain-node を subprocess で起動する
    # Then: /healthz が 200 を返す
    config_path, observability_port = production_config
    monkeypatch.setenv("EASYBLOCKCHAIN_OBSERVABILITY_TOKEN", TEST_TOKEN)
    env = os.environ.copy()
    env["EASYBLOCKCHAIN_OBSERVABILITY_TOKEN"] = TEST_TOKEN

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "useful_blockchain.cli",
            "--config",
            str(config_path),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 15.0
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                stderr = proc.stderr.read() if proc.stderr else ""
                raise AssertionError(
                    f"CLI process exited early with code {proc.returncode}: {stderr}"
                )
            try:
                if _sync_http_status("127.0.0.1", observability_port, "/healthz") == 200:
                    return
            except OSError as exc:
                last_error = exc
            time.sleep(0.2)
        raise AssertionError(f"healthz did not return 200 in time: {last_error}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
