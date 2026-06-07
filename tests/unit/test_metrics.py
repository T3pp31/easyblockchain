from useful_blockchain.observability.metrics import MetricsCollector
from useful_blockchain.types import ObservabilitySettings


def test_metrics_disabled_returns_empty_payload():
    # Given: observability が無効
    # When: render を呼ぶ
    # Then: 空バイト列が返る
    collector = MetricsCollector(ObservabilitySettings(enabled=False))
    assert collector.render() == b""


def test_metrics_enabled_with_prometheus():
    # Given: observability が有効
    # When: メトリクス更新と render を呼ぶ
    # Then: Prometheus 形式のメトリクスが返る
    collector = MetricsCollector(ObservabilitySettings(enabled=True))
    collector.set_chain_height(3)
    collector.set_peer_count(2)
    collector.inc_blocks_accepted()
    collector.inc_sync_operations()
    collector.inc_pong_timeouts()
    payload = collector.render()
    if collector.metrics_enabled:
        assert b"ebc_chain_height" in payload
    else:
        assert payload == b""
