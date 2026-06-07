import asyncio
import subprocess
from pathlib import Path

import pytest

from useful_blockchain.network.node import Node


def _generate_self_signed_cert(cert_dir: Path) -> tuple[str, str]:
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )
    return str(cert_path), str(key_path)


def _pow_overrides(
    port: int,
    data_suffix: str,
    *,
    bootstrap: list[str] | None = None,
    tls: dict | None = None,
) -> dict:
    network: dict = {
        "host": "127.0.0.1",
        "port": port,
        "bootstrap_peers": bootstrap or [],
        "ping_interval_seconds": 60,
        "reconnect": {"enabled": False},
    }
    if tls is not None:
        network["tls"] = tls
    return {
        "consensus": {
            "type": "pow",
            "pow": {"initial_difficulty": 1, "max_mining_iterations": 200000},
        },
        "network": network,
        "node": {"data_dir": f"/tmp/ebc-wss-test-{data_suffix}"},
    }


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_wss_two_node_pow_sync(tmp_path: Path) -> None:
    # Given: TLS 有効なノード1と、wss で接続するノード2
    # When: ノード1がブロックを追加しノード2が同期する
    # Then: 両ノードのチェーン高さが1以上になる
    cert_file, key_file = _generate_self_signed_cert(tmp_path)

    node1 = Node(
        overrides=_pow_overrides(
            0,
            "n1",
            tls={
                "enabled": True,
                "cert_file": cert_file,
                "key_file": key_file,
                "verify_peer": False,
            },
        )
    )
    await node1.start()
    url1 = node1.p2p.local_url
    assert url1.startswith("wss://")

    node2 = Node(
        overrides=_pow_overrides(
            0,
            "n2",
            bootstrap=[url1],
            tls={"enabled": False, "verify_peer": False},
        )
    )
    await node2.start()

    await node1.add_block(["alice"], ["bob"])
    await asyncio.sleep(0.5)
    await node2.sync_chain()
    await asyncio.sleep(0.5)

    assert node1.chain_height >= 1
    assert node2.chain_height >= 1

    await node2.stop()
    await node1.stop()
