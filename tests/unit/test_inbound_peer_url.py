from __future__ import annotations

from types import SimpleNamespace

import pytest

from useful_blockchain.hash_utils import genesis_hash
from useful_blockchain.network.node import Node
from useful_blockchain.network.peer_auth import build_hello_payload, verify_hello
from useful_blockchain.signature import SignatureManager
from useful_blockchain.types import DEFAULT_GENESIS_PREV_HASH, PeerAuthSettings


def _signed_payload(advertised_url: str | None) -> dict:
    manager = SignatureManager()
    manager.generate_key_pair()
    return build_hello_payload(
        "node-b",
        "pow",
        5,
        genesis_hash([], DEFAULT_GENESIS_PREV_HASH),
        manager,
        advertised_url=advertised_url,
    )


class _FakePeer:
    def __init__(self) -> None:
        self.closed = False
        self.close_calls = 0

    def mark_authenticated(self) -> None:
        return None

    async def close(self) -> None:
        self.close_calls += 1
        self.closed = True


def _make_node() -> Node:
    node = Node.__new__(Node)
    node.p2p = SimpleNamespace(
        peers={"peer-inbound-1": _FakePeer()},
        local_url="ws://127.0.0.1:9000",
    )
    node.blockchain = SimpleNamespace(chain=[])
    node.settings = SimpleNamespace(
        network=SimpleNamespace(peer_auth=PeerAuthSettings(enabled=True)),
        consensus=SimpleNamespace(type="pow"),
        genesis=SimpleNamespace(prev_hash=DEFAULT_GENESIS_PREV_HASH),
    )
    node._active_urls = set()
    node._url_by_peer = {}

    async def _noop_send_hello(_peer_id: str) -> None:
        return None

    async def _noop_request_chain(_peer_id: str) -> None:
        return None

    node._send_hello = _noop_send_hello  # type: ignore[method-assign]
    node._request_chain = _noop_request_chain  # type: ignore[method-assign]
    return node


def test_build_hello_payload_includes_advertised_url_and_verifies() -> None:
    # Given: advertised_url を指定して HELLO ペイロードを構築する
    # When: ペイロードを検証する
    # Then: advertised_url が含まれ、署名検証は通る
    payload = _signed_payload("ws://peer-b:9000")

    assert payload["advertised_url"] == "ws://peer-b:9000"
    assert verify_hello(payload, PeerAuthSettings(enabled=True))


def test_build_hello_payload_without_advertised_url_omits_field() -> None:
    # Given: advertised_url を指定しない
    # When: ペイロードを構築する
    # Then: advertised_url フィールドは含まれない
    payload = _signed_payload(None)

    assert "advertised_url" not in payload
    assert verify_hello(payload, PeerAuthSettings(enabled=True))


@pytest.mark.asyncio
async def test_inbound_hello_registers_advertised_url() -> None:
    # Given: advertised_url を含む有効な HELLO
    # When: _on_hello を呼ぶ
    # Then: advertised_url が _active_urls に登録され、同 URL への重複接続が防がれる
    node = _make_node()
    payload = _signed_payload("ws://peer-b:9000")

    await node._on_hello("peer-inbound-1", payload)

    assert node._active_urls == {"ws://peer-b:9000"}
    assert node._url_by_peer["peer-inbound-1"] == "ws://peer-b:9000"


@pytest.mark.asyncio
async def test_inbound_hello_ignores_local_url_and_invalid_url() -> None:
    # Given: advertised_url が自分の URL または不正な形式の HELLO
    # When: _on_hello を呼ぶ
    # Then: _active_urls には何も登録されない
    node = _make_node()

    await node._on_hello("peer-inbound-1", _signed_payload("ws://127.0.0.1:9000"))
    assert node._active_urls == set()

    await node._on_hello("peer-inbound-1", _signed_payload("http://peer-b:9000"))
    assert node._active_urls == set()
