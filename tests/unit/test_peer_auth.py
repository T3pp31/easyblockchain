import time

from useful_blockchain.network.peer_auth import (
    build_hello_payload,
    hello_signing_payload,
    verify_hello,
)
from useful_blockchain.signature import SignatureManager
from useful_blockchain.types import PeerAuthSettings


def test_build_and_verify_hello_success():
    # Given: 有効な鍵ペアと HELLO フィールド
    # When: build_hello_payload で署名し verify_hello で検証する
    # Then: 検証が成功する
    manager = SignatureManager()
    manager.generate_key_pair()
    payload = build_hello_payload(
        "node-1",
        "pow",
        0,
        "a" * 64,
        manager,
    )
    settings = PeerAuthSettings(enabled=True, max_skew_seconds=300)
    assert verify_hello(payload, settings) is True


def test_verify_hello_rejects_tampered_signature():
    # Given: 正当な HELLO ペイロード
    # When: 署名を改ざんして検証する
    # Then: 検証が失敗する
    manager = SignatureManager()
    manager.generate_key_pair()
    payload = build_hello_payload("node-1", "pow", 0, "b" * 64, manager)
    payload["signature"] = "00" * 128
    settings = PeerAuthSettings()
    assert verify_hello(payload, settings) is False


def test_verify_hello_rejects_expired_timestamp():
    # Given: 古いタイムスタンプの HELLO
    # When: 許容ウィンドウ外で検証する
    # Then: 検証が失敗する
    manager = SignatureManager()
    manager.generate_key_pair()
    payload = build_hello_payload("node-1", "pow", 0, "c" * 64, manager)
    settings = PeerAuthSettings(max_skew_seconds=10)
    old_now = time.time() - 100
    assert verify_hello(payload, settings, now=old_now) is False


def test_verify_hello_rejects_missing_fields():
    # Given: 必須フィールドが欠けたペイロード
    # When: verify_hello を呼ぶ
    # Then: 検証が失敗する
    settings = PeerAuthSettings()
    assert verify_hello({"node_id": "x"}, settings) is False


def test_hello_signing_payload_excludes_chain_height():
    # Given: chain_height を含むペイロード
    # When: hello_signing_payload を取得する
    # Then: 署名対象に chain_height が含まれない
    payload = {
        "node_id": "n1",
        "consensus_type": "pow",
        "genesis_hash": "d" * 64,
        "timestamp": 123,
        "chain_height": 99,
    }
    signing = hello_signing_payload(payload)
    assert "chain_height" not in signing
    assert signing["timestamp"] == 123
