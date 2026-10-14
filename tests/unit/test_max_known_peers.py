from useful_blockchain.network.discovery import PeerDiscovery
from useful_blockchain.types import NetworkSettings, PeerConnectSettings


def _discovery(max_known_peers: int) -> PeerDiscovery:
    settings = NetworkSettings(
        peer_connect=PeerConnectSettings(
            allow_private_ips=True,
            max_known_peers=max_known_peers,
            allowed_ports=[80, 443, 8765],
        )
    )
    return PeerDiscovery(settings, "ws://127.0.0.1:9000", "development")


def _urls(count: int) -> list[str]:
    return [f"ws://127.0.0.1:{9700 + i}" for i in range(count)]


def test_known_peers_evicted_beyond_max_known_peers() -> None:
    # Given: max_known_peers=5 の discovery
    # When: 8 件の URL を追加する
    # Then: known_peers は 5 件で、最も新しい 5 件が残る
    discovery = _discovery(max_known_peers=5)
    for url in _urls(8):
        discovery.add_peer(url)

    assert discovery.known_peers == sorted(_urls(8)[-5:])


def test_readding_existing_peer_refreshes_eviction_order() -> None:
    # Given: max_known_peers=3 で既に 3 件追加済み
    # When: 最古の URL を再追加してから新しい URL を追加する
    # Then: 再追加した URL は残り、2 番目に古い URL が追い出される
    discovery = _discovery(max_known_peers=3)
    urls = _urls(3)
    for url in urls:
        discovery.add_peer(url)

    discovery.add_peer(urls[0])
    discovery.add_peer("ws://127.0.0.1:9799")

    assert discovery.known_peers == sorted(
        [urls[0], urls[2], "ws://127.0.0.1:9799"]
    )


def test_default_max_known_peers_keeps_large_set() -> None:
    # Given: デフォルト設定 (max_known_peers=1000)
    # When: 1000 件追加する
    # Then: 全件保持される
    discovery = _discovery(max_known_peers=PeerConnectSettings().max_known_peers)
    for url in _urls(1000):
        discovery.add_peer(url)

    assert len(discovery.known_peers) == 1000
