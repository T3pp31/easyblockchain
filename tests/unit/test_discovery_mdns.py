from unittest.mock import MagicMock

from useful_blockchain.network.discovery import PeerDiscovery, _mdns_tls_enabled
from useful_blockchain.types import NetworkSettings, TlsSettings


def test_mdns_tls_enabled_reads_txt_flag() -> None:
    # Given: TXT レコードに tls=1 が含まれる
    # When: フラグを解釈する
    # Then: TLS 有効と判定される
    assert _mdns_tls_enabled({b"tls": b"1"}) is True


def test_mdns_tls_enabled_false_when_flag_absent() -> None:
    # Given: TXT レコードに tls フラグがない
    # When: フラグを解釈する
    # Then: TLS 無効と判定される
    assert _mdns_tls_enabled(None) is False
    assert _mdns_tls_enabled({}) is False
    assert _mdns_tls_enabled({b"tls": b"0"}) is False


def test_register_self_advertises_tls_flag(tmp_path=None) -> None:
    # Given: TLS 有効な設定
    # When: _register_self を呼ぶ
    # Then: TXT に tls=1 を持つ ServiceInfo が登録される
    discovery = PeerDiscovery(
        NetworkSettings(tls=TlsSettings(enabled=True)),
        "wss://127.0.0.1:8765",
        "development",
    )
    zc = MagicMock()
    discovery._register_self(zc)
    info = zc.register_service.call_args[0][0]
    assert info.properties == {b"tls": b"1"}
    assert info.port == 8765


def test_register_self_advertises_tls_disabled(tmp_path=None) -> None:
    # Given: TLS 無効な設定
    # When: _register_self を呼ぶ
    # Then: TXT に tls=0 が登録される
    discovery = PeerDiscovery(
        NetworkSettings(), "ws://127.0.0.1:8765", "development"
    )
    zc = MagicMock()
    discovery._register_self(zc)
    info = zc.register_service.call_args[0][0]
    assert info.properties == {b"tls": b"0"}


def _enabled_discovery():
    from useful_blockchain.types import PeerConnectSettings
    return PeerDiscovery(NetworkSettings(
        mdns_enabled=True,
        mdns_max_pending_services=2,
        mdns_resolution_interval_seconds=0.01,
        mdns_resolution_timeout_seconds=0.1,
        peer_connect=PeerConnectSettings(allow_private_ips=True, blocked_cidrs=[]),
    ), "ws://127.0.0.1:9000")


def test_browser_start_failure_closes_zeroconf(monkeypatch):
    import zeroconf
    # Given: Zeroconf 作成後にブラウザ構築が失敗する環境
    discovery = _enabled_discovery()
    zc = MagicMock()
    monkeypatch.setattr(zeroconf, "Zeroconf", lambda: zc)
    monkeypatch.setattr(zeroconf, "ServiceBrowser", MagicMock(side_effect=ValueError("bad service type")))
    # When: mDNS を開始する
    discovery.start_mdns()
    # Then: ソケットを解放し、停止時に再解放しない
    zc.close.assert_called_once()
    assert discovery._mdns is None
    discovery.stop_mdns()
    zc.close.assert_called_once()


def test_mdns_resolution_does_not_block_listener_and_queue_is_bounded(monkeypatch):
    import socket
    import threading
    import zeroconf
    from types import SimpleNamespace
    # Given: 解決 API が待機中の専用ワーカー
    discovery = _enabled_discovery()
    entered, release, found = threading.Event(), threading.Event(), threading.Event()
    zc, browser = MagicMock(), MagicMock()
    captured = {}
    original_worker = discovery._resolve_mdns_services

    def worker(zc, requests, stop, callback):
        captured["requests"] = requests
        original_worker(zc, requests, stop, callback)

    def resolve(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return SimpleNamespace(addresses=[socket.inet_aton("127.0.0.1")], port=8765, properties={})

    def make_browser(zc, service, listener):
        captured["listener"] = listener
        return browser

    monkeypatch.setattr(discovery, "_resolve_mdns_services", worker)
    monkeypatch.setattr(discovery, "_register_self", lambda zc: None)
    monkeypatch.setattr(zeroconf, "Zeroconf", lambda: zc)
    monkeypatch.setattr(zeroconf, "ServiceBrowser", make_browser)
    zc.get_service_info.side_effect = resolve
    discovery.start_mdns(lambda url: found.set())
    resolver_thread = discovery._mdns_worker
    try:
        # When: リスナーに解決不能なサービスを連投する
        listener = captured["listener"]
        listener.add_service(zc, "type", "first")
        assert entered.wait(1)
        for i in range(100):
            listener.add_service(zc, "type", f"fake-{i}")
        # Then: 解決待機に関係なくコールバックが戻り、キューは上限以内
        assert captured["requests"].qsize() == 2
        release.set()
        assert found.wait(1)
        assert "ws://127.0.0.1:8765" in discovery.known_peers
        assert zc.get_service_info.call_args.kwargs["timeout"] == 100
    finally:
        release.set()
        discovery.stop_mdns()
    assert not resolver_thread.is_alive()
    browser.cancel.assert_called_once()
    zc.close.assert_called_once()
    # When: 停止後に遅延コールバックが到着する
    size = captured["requests"].qsize()
    captured["listener"].add_service(zc, "type", "late")
    # Then: 新しい解決要求は登録されない
    assert captured["requests"].qsize() == size


def test_mdns_resolver_limits_attempts_and_recovers_from_failure():
    import queue
    from types import SimpleNamespace
    from unittest.mock import Mock
    # Given: 解決エラー・未解決サービス・不正アドレスを含むキュー
    discovery = _enabled_discovery()
    requests = queue.Queue()
    for i in range(3):
        requests.put(("type", str(i)))
    stop = SimpleNamespace(is_set=lambda: False, wait=Mock(side_effect=[False, False, True]))
    zc = MagicMock()
    zc.get_service_info.side_effect = [OSError("resolution error"), None,
                                     SimpleNamespace(addresses=[b"bad"], port=8765, properties={})]
    callback = Mock()
    # When: 解決ワーカーを実行する（待機はモックで制御）
    discovery._resolve_mdns_services(zc, requests, stop, callback)
    # Then: エラーで停止せず、試行ごとに設定済みの間隔を守る
    assert zc.get_service_info.call_count == 3
    assert stop.wait.call_count == 3
    assert all(call.args == (0.01,) for call in stop.wait.call_args_list)
    callback.assert_not_called()


def test_mdns_register_failure_stops_worker_and_browser(monkeypatch):
    import zeroconf
    # Given: ブラウザ・ワーカー開始後の広告処理に失敗する環境
    discovery = _enabled_discovery()
    zc, browser = MagicMock(), MagicMock()
    monkeypatch.setattr(zeroconf, "Zeroconf", lambda: zc)
    monkeypatch.setattr(zeroconf, "ServiceBrowser", lambda *args: browser)
    monkeypatch.setattr(discovery, "_register_self", MagicMock(side_effect=ValueError("bad advertisement")))
    # When: 開始途中で例外が発生する
    discovery.start_mdns()
    # Then: 途中まで開始したリソースを解放する
    browser.cancel.assert_called_once()
    zc.close.assert_called_once()
    assert discovery._mdns is None and discovery._mdns_worker is None


def test_mdns_browser_cancel_failure_still_closes_zeroconf():
    # Given: cancel が失敗する開始済みブラウザ
    discovery = _enabled_discovery()
    zc, browser = MagicMock(), MagicMock()
    browser.cancel.side_effect = OSError("cancel failed")
    discovery._mdns = (zc, browser)
    # When: 停止する
    discovery.stop_mdns()
    # Then: 残りのソケット解放を続行する
    zc.close.assert_called_once()
    assert discovery._mdns is None
