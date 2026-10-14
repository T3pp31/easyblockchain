from useful_blockchain.network.reconnect import ReconnectManager
from useful_blockchain.types import ReconnectSettings


def test_reconnect_should_retry_when_no_failures():
    # Given: 失敗記録のない URL
    # When: should_retry を呼ぶ
    # Then: 再接続を試行すべきと判定される
    manager = ReconnectManager(ReconnectSettings())
    assert manager.should_retry("ws://127.0.0.1:8765", now=0.0) is True


def test_reconnect_backoff_delays_retry():
    # Given: 接続失敗を1回記録した URL
    # When: バックオフ期間内に should_retry を呼ぶ
    # Then: 再接続しない
    settings = ReconnectSettings(initial_delay_seconds=5.0, backoff_multiplier=2.0)
    manager = ReconnectManager(settings)
    manager.record_failure("ws://127.0.0.1:8765", now=10.0)
    assert manager.should_retry("ws://127.0.0.1:8765", now=12.0) is False
    assert manager.should_retry("ws://127.0.0.1:8765", now=16.0) is True


def test_reconnect_success_resets_state():
    # Given: 失敗記録後に成功した URL
    # When: should_retry を呼ぶ
    # Then: 即座に再接続可能
    manager = ReconnectManager(ReconnectSettings())
    manager.record_failure("ws://127.0.0.1:8765", now=1.0)
    manager.record_success("ws://127.0.0.1:8765")
    assert manager.should_retry("ws://127.0.0.1:8765", now=1.5) is True


def test_reconnect_max_attempts_stops_retry():
    # Given: max_attempts=2 で2回失敗した URL
    # When: should_retry を呼ぶ
    # Then: 再接続しない
    settings = ReconnectSettings(max_attempts=2, initial_delay_seconds=1.0)
    manager = ReconnectManager(settings)
    manager.record_failure("ws://127.0.0.1:8765", now=0.0)
    manager.record_failure("ws://127.0.0.1:8765", now=1.0)
    assert manager.should_retry("ws://127.0.0.1:8765", now=100.0) is False


def test_reconnect_backoff_does_not_overflow_on_many_failures():
    # Given: max_attempts=0（無制限）の設定
    # When: 同一 URL で約1100回失敗を記録する
    # Then: OverflowError が発生せず、遅延は max_delay にクランプされる
    settings = ReconnectSettings(
        initial_delay_seconds=1.0,
        backoff_multiplier=2.0,
        max_delay_seconds=60.0,
        max_attempts=0,
    )
    manager = ReconnectManager(settings)
    for i in range(1100):
        manager.record_failure("ws://127.0.0.1:8765", now=float(i))
    assert manager.should_retry("ws://127.0.0.1:8765", now=1099.0) is False
    assert manager.should_retry("ws://127.0.0.1:8765", now=1099.0 + 60.0) is True


def test_reconnect_backoff_delay_capped_at_max_delay():
    # Given: 初期遅延1秒・倍率2.0・最大遅延60秒の設定
    # When: 失敗を7回記録する（指数6で 2**6=64 > 60）
    # Then: 次回リトライ時刻は初期時刻 + max_delay にクランプされる
    settings = ReconnectSettings(
        initial_delay_seconds=1.0,
        backoff_multiplier=2.0,
        max_delay_seconds=60.0,
    )
    manager = ReconnectManager(settings)
    for i in range(7):
        manager.record_failure("ws://127.0.0.1:8765", now=0.0)
    assert manager.should_retry("ws://127.0.0.1:8765", now=59.0) is False
    assert manager.should_retry("ws://127.0.0.1:8765", now=60.0) is True
