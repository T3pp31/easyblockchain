import threading

from useful_blockchain.network.discovery import PeerDiscovery
from useful_blockchain.types import NetworkSettings, PeerConnectSettings


def _discovery() -> PeerDiscovery:
    settings = NetworkSettings(
        peer_connect=PeerConnectSettings(
            allow_private_ips=True,
            allowed_ports=[80, 443, 8765],
        )
    )
    return PeerDiscovery(settings, "ws://127.0.0.1:9000", "development")


def test_known_peers_safe_under_concurrent_add_and_read() -> None:
    # Given: mDNS リスナースレッドから add_peer が並行実行される状態
    # When: 別スレッドが add_peer を連続実行する間に known_peers を繰り返し読む
    # Then: Set changed size during iteration などの RuntimeError は発生しない
    discovery = _discovery()
    errors: list[Exception] = []

    def writer() -> None:
        for i in range(500):
            discovery.add_peer(f"ws://127.0.0.1:{8700 + (i % 60)}")

    def reader() -> None:
        try:
            for _ in range(500):
                _ = discovery.known_peers
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


def test_concurrent_add_peer_keeps_all_valid_urls() -> None:
    # Given: 複数スレッドから同一・異なる URL が並行追加される
    # When: 全スレッドの完了を待つ
    # Then: 期待した全 URL が known_peers に含まれる
    discovery = _discovery()
    expected = [f"ws://127.0.0.1:{8700 + i}" for i in range(20)]

    def writer() -> None:
        for url in expected:
            discovery.add_peer(url)
            discovery.add_peer(url)

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert discovery.known_peers == sorted(expected)
