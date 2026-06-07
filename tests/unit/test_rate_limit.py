from useful_blockchain.network.rate_limit import SlidingWindowRateLimiter


def test_sliding_window_allows_up_to_max_events():
    # Given: 1秒あたり最大2件のリミッター
    # When: 2件までイベントを記録する
    # Then: いずれも許可される
    limiter = SlidingWindowRateLimiter(max_events=2, window_seconds=1.0)
    assert limiter.allow("ip-1", now=100.0) is True
    assert limiter.allow("ip-1", now=100.1) is True


def test_sliding_window_blocks_excess_events():
    # Given: 上限に達したリミッター
    # When: 追加イベントを記録する
    # Then: 拒否される
    limiter = SlidingWindowRateLimiter(max_events=2, window_seconds=1.0)
    limiter.allow("ip-1", now=100.0)
    limiter.allow("ip-1", now=100.1)
    assert limiter.allow("ip-1", now=100.2) is False


def test_sliding_window_expires_old_events():
    # Given: ウィンドウ外の古いイベント
    # When: 新しいウィンドウでイベントを記録する
    # Then: 再び許可される
    limiter = SlidingWindowRateLimiter(max_events=1, window_seconds=1.0)
    limiter.allow("ip-1", now=100.0)
    assert limiter.allow("ip-1", now=100.5) is False
    assert limiter.allow("ip-1", now=101.1) is True


def test_sliding_window_reset_clears_key():
    # Given: ブロック済みのキー
    # When: reset を呼ぶ
    # Then: 再び許可される
    limiter = SlidingWindowRateLimiter(max_events=1, window_seconds=10.0)
    limiter.allow("ip-1", now=1.0)
    assert limiter.allow("ip-1", now=1.1) is False
    limiter.reset("ip-1")
    assert limiter.allow("ip-1", now=1.2) is True
