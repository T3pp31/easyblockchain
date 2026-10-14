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
    # Given: 検証時刻より古い（期限切れの）タイムスタンプの HELLO
    # When: 許容ウィンドウ外で検証する
    # Then: 検証が失敗する
    manager = SignatureManager()
    manager.generate_key_pair()
    payload = build_hello_payload("node-1", "pow", 0, "c" * 64, manager)
    settings = PeerAuthSettings(max_skew_seconds=10)
    future_now = time.time() + 100
    assert verify_hello(payload, settings, now=future_now) is False


def test_verify_hello_rejects_future_timestamp():
    # Given: 検証時刻より未来のタイムスタンプの HELLO
    # When: 許容ウィンドウ外で検証する
    # Then: 検証が失敗する
    manager = SignatureManager()
    manager.generate_key_pair()
    payload = build_hello_payload("node-1", "pow", 0, "c" * 64, manager)
    settings = PeerAuthSettings(max_skew_seconds=10)
    past_now = time.time() - 100
    assert verify_hello(payload, settings, now=past_now) is False


def test_verify_hello_rejects_missing_fields():
    # Given: 必須フィールドが欠けたペイロード
    # When: verify_hello を呼ぶ
    # Then: 検証が失敗する
    settings = PeerAuthSettings()
    assert verify_hello({"node_id": "x"}, settings) is False


def test_verify_hello_rejects_malformed_public_key():
    # Given: 不正な PEM の public_key を含む HELLO
    # When: verify_hello を呼ぶ
    # Then: 例外ではなく False が返る
    manager = SignatureManager()
    manager.generate_key_pair()
    payload = build_hello_payload("node-1", "pow", 0, "d" * 64, manager)
    payload["public_key"] = "garbage-not-a-key"
    settings = PeerAuthSettings()
    assert verify_hello(payload, settings) is False


def test_verify_hello_rejects_non_rsa_public_key():
    # Given: RSA 以外の公開鍵を含む HELLO
    # When: verify_hello を呼ぶ
    # Then: 例外ではなく False が返る
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    manager = SignatureManager()
    manager.generate_key_pair()
    payload = build_hello_payload("node-1", "pow", 0, "e" * 64, manager)
    ec_private_key = ec.generate_private_key(ec.SECP256R1())
    payload["public_key"] = ec_private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    settings = PeerAuthSettings()
    assert verify_hello(payload, settings) is False


def test_verify_hello_rejects_non_string_signature_and_public_key():
    # Given: signature / public_key が文字列以外の HELLO
    # When: verify_hello を呼ぶ
    # Then: 例外ではなく False が返る
    manager = SignatureManager()
    manager.generate_key_pair()
    settings = PeerAuthSettings()

    payload = build_hello_payload("node-1", "pow", 0, "f" * 64, manager)
    payload["signature"] = None
    assert verify_hello(payload, settings) is False

    payload = build_hello_payload("node-1", "pow", 0, "f" * 64, manager)
    payload["public_key"] = None
    assert verify_hello(payload, settings) is False


def test_hello_signing_payload_includes_chain_height():
    # Given: chain_height を含むペイロード
    # When: hello_signing_payload を取得する
    # Then: 署名対象に chain_height が含まれる
    payload = {
        "node_id": "n1",
        "consensus_type": "pow",
        "genesis_hash": "d" * 64,
        "timestamp": 123,
        "chain_height": 99,
    }
    signing = hello_signing_payload(payload)
    assert signing["chain_height"] == 99
    assert signing["timestamp"] == 123


def test_build_and_verify_hello_with_advertised_url():
    # Given: advertised_url を含む HELLO
    # When: build_hello_payload で署名し verify_hello で検証する
    # Then: 検証が成功する
    manager = SignatureManager()
    manager.generate_key_pair()
    payload = build_hello_payload(
        "node-1",
        "pow",
        0,
        "e" * 64,
        manager,
        advertised_url="ws://peer-a:9000",
    )
    settings = PeerAuthSettings(enabled=True, max_skew_seconds=300)
    assert verify_hello(payload, settings) is True


def test_verify_hello_rejects_tampered_advertised_url():
    # Given: advertised_url を含む正当な HELLO
    # When: advertised_url を改ざんして検証する
    # Then: 検証が失敗する
    manager = SignatureManager()
    manager.generate_key_pair()
    payload = build_hello_payload(
        "node-1",
        "pow",
        0,
        "f" * 64,
        manager,
        advertised_url="ws://peer-a:9000",
    )
    payload["advertised_url"] = "ws://evil:9000"
    settings = PeerAuthSettings()
    assert verify_hello(payload, settings) is False


def test_verify_hello_rejects_non_numeric_timestamp():
    # Given: 数値変換できない timestamp
    # When: verify_hello を呼ぶ
    # Then: 例外ではなく False が返る
    manager = SignatureManager()
    manager.generate_key_pair()
    payload = build_hello_payload("node-1", "pow", 0, "c" * 64, manager)
    settings = PeerAuthSettings(max_skew_seconds=10)
    for bad in ("abc", None, [1], float("inf")):
        payload["timestamp"] = bad
        assert verify_hello(payload, settings) is False

def test_verify_hello_rejects_invalid_public_key():
    # Given: 不正な PEM の public_key
    # When: verify_hello を呼ぶ
    # Then: 例外ではなく False が返る
    manager = SignatureManager()
    manager.generate_key_pair()
    payload = build_hello_payload("node-1", "pow", 0, "c" * 64, manager)
    settings = PeerAuthSettings(max_skew_seconds=10)
    payload["public_key"] = "not a pem"
    assert verify_hello(payload, settings) is False


def test_verify_hello_rejects_tampered_or_invalid_chain_height():
    # Given: 正当な署名付き HELLO
    manager = SignatureManager()
    manager.generate_key_pair()
    payload = build_hello_payload("node-1", "pow", 1, "a" * 64, manager)
    # When: chain_height のみを変更・削除する
    # Then: 署名検証は例外なく失敗する
    for height in (2, -1, None, "1", True, float("inf"), float("nan")):
        assert verify_hello({**payload, "chain_height": height}, PeerAuthSettings()) is False
    del payload["chain_height"]
    assert verify_hello(payload, PeerAuthSettings()) is False
