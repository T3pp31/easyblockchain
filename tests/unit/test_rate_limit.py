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


def test_stale_keys_are_pruned_from_events():
    # Given: window_seconds 以上アクセスのないキー
    # When: 次のキー操作で一括掃除が走る
    # Then: 古いキーのエントリは削除され、最近のキーは残る
    limiter = SlidingWindowRateLimiter(max_events=10, window_seconds=1.0)
    limiter.allow("old", now=100.0)
    limiter.allow("recent", now=100.5)
    limiter.allow("recent", now=101.4)
    assert "old" not in limiter._events
    assert "old" not in limiter._last_access
    assert "recent" in limiter._events


def test_pruned_key_can_be_allowed_again():
    # Given: ブロック後、長時間アクセスのなかったキー
    # When: 再び allow を呼ぶ
    # Then: 掃除済みで新規キーとして扱われ許可される
    limiter = SlidingWindowRateLimiter(max_events=1, window_seconds=1.0)
    limiter.allow("ip-1", now=100.0)
    assert limiter.allow("ip-1", now=100.1) is False
    assert limiter.allow("ip-1", now=101.2) is True
