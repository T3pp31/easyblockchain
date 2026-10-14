from __future__ import annotations
import asyncio
import logging
from useful_blockchain.network.rate_limit import SlidingWindowRateLimiter
from useful_blockchain.types import RateLimitSettings

import pytest
from websockets.exceptions import ConnectionClosed, PayloadTooBig

from useful_blockchain.network.messages import MessageType, encode_message
from useful_blockchain.network.peer import PeerConnection


class _MockWebSocket:
    def __init__(self, messages: list[str], *, raise_on_iter: Exception | None = None) -> None:
        self._messages = list(messages)
        self._raise_on_iter = raise_on_iter
        self.closed = False

    def __aiter__(self) -> "_MockWebSocket":
        return self

    async def __anext__(self) -> str:
        if self._raise_on_iter is not None:
            raise self._raise_on_iter
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)

    async def close(self, *args, **kwargs) -> None:
        self.closed = True

    async def send(self, _data: str) -> None:
        return None


@pytest.mark.asyncio
async def test_listen_skips_invalid_json_and_processes_next_message() -> None:
    # Given: 不正 JSON の後に有効な PING メッセージ
    # When: listen を実行する
    # Then: 有効メッセージのみハンドラに渡る
    handled: list[MessageType] = []

    async def on_message(_peer_id: str, msg_type: MessageType, _payload: dict) -> None:
        handled.append(msg_type)

    ws = _MockWebSocket(["not-json", encode_message(MessageType.PING, {})])
    peer = PeerConnection("peer-1", ws, on_message, require_auth=False)
    await peer.listen()

    assert handled == [MessageType.PING]
    assert peer.closed


@pytest.mark.asyncio
async def test_listen_skips_unknown_type_and_processes_next_message() -> None:
    # Given: 未知 type の後に有効な PONG メッセージ
    # When: listen を実行する
    # Then: 有効メッセージのみハンドラに渡る
    handled: list[MessageType] = []

    async def on_message(_peer_id: str, msg_type: MessageType, _payload: dict) -> None:
        handled.append(msg_type)

    ws = _MockWebSocket(
        ['{"type": "UNKNOWN"}', encode_message(MessageType.PONG, {})],
    )
    peer = PeerConnection("peer-2", ws, on_message, require_auth=False)
    await peer.listen()

    assert handled == [MessageType.PONG]
    assert peer.closed


@pytest.mark.asyncio
async def test_listen_handles_payload_too_large() -> None:
    # Given: WebSocket イテレーションで PayloadTooBig が発生
    # When: listen を実行する
    # Then: 接続は閉じ状態になり例外は外に漏れない
    async def on_message(_peer_id: str, _msg_type: MessageType, _payload: dict) -> None:
        return None

    ws = _MockWebSocket([], raise_on_iter=PayloadTooBig(1024, 512))
    peer = PeerConnection("peer-3", ws, on_message, require_auth=False)
    await peer.listen()

    assert peer.closed


@pytest.mark.asyncio
async def test_send_skips_oversized_message() -> None:
    # Given: max_message_bytes より大きいペイロード
    # When: send を呼ぶ
    # Then: WebSocket には送信されない
    sent: list[str] = []

    class _RecordingWebSocket(_MockWebSocket):
        async def send(self, data: str) -> None:
            sent.append(data)

    ws = _RecordingWebSocket([])
    peer = PeerConnection(
        "peer-4", ws, lambda *_: None, max_message_bytes=32, require_auth=False
    )
    huge_payload = {"data": "x" * 100}
    await peer.send(MessageType.HELLO, huge_payload)

    assert sent == []


@pytest.mark.asyncio
async def test_listen_rejects_message_before_hello_when_auth_required() -> None:
    # Given: 認証必須のピア接続
    # When: HELLO 以外のメッセージを受信する
    # Then: ハンドラは呼ばれず接続が閉じる
    handled: list[MessageType] = []

    async def on_message(_peer_id: str, msg_type: MessageType, _payload: dict) -> None:
        handled.append(msg_type)

    ws = _MockWebSocket([encode_message(MessageType.PING, {})])
    peer = PeerConnection("peer-5", ws, on_message, require_auth=True)
    await peer.listen()

    assert handled == []
    assert peer.closed


@pytest.mark.asyncio
async def test_send_swallows_connection_closed() -> None:
    # Given: 送信時に相手が切断した（ConnectionClosed が発生する）WebSocket
    # When: send を呼ぶ
    # Then: 例外は漏れず no-op として完了する
    class _ClosedWebSocket(_MockWebSocket):
        async def send(self, _data: str) -> None:
            raise ConnectionClosed(None, None)

    ws = _ClosedWebSocket([])
    peer = PeerConnection("peer-6", ws, lambda *_: None, require_auth=False)
    await peer.send(MessageType.HELLO, {"node_id": "n1"})


@pytest.mark.asyncio
async def test_shared_message_limiter_aggregates_across_connections() -> None:
    # Given: 同一キーを共有するリミッターと 2 つの接続（同一送信元を模擬）
    # When: 合計で上限を超えるメッセージを送る
    # Then: 上限超過の接続は閉じられ、ピア単位で集約される
    limiter = SlidingWindowRateLimiter(2, window_seconds=1.0)
    settings = RateLimitSettings(max_messages_per_peer_per_second=2)

    handled: list[MessageType] = []

    async def on_message(_peer_id: str, msg_type: MessageType, _payload: dict) -> None:
        handled.append(msg_type)

    ws1 = _MockWebSocket(
        [encode_message(MessageType.PING, {}), encode_message(MessageType.PING, {})]
    )
    peer1 = PeerConnection(
        "conn-1",
        ws1,
        on_message,
        require_auth=False,
        rate_limit_settings=settings,
        message_limiter=limiter,
        rate_limit_key="203.0.113.7",
    )
    await peer1.listen()
    assert handled == [MessageType.PING, MessageType.PING]

    ws2 = _MockWebSocket([encode_message(MessageType.PING, {})])
    peer2 = PeerConnection(
        "conn-2",
        ws2,
        on_message,
        require_auth=False,
        rate_limit_settings=settings,
        message_limiter=limiter,
        rate_limit_key="203.0.113.7",
    )
    await peer2.listen()

    # conn-2 は同一キーの集計により上限超過で閉じられる
    assert peer2.closed is True
    assert handled == [MessageType.PING, MessageType.PING]


@pytest.mark.asyncio
async def test_listen_closes_websocket_on_handler_exception() -> None:
    # Given: on_message ハンドラが例外を送出する
    # When: 有効なメッセージを受信して listen を実行する
    # Then: 例外は漏れず、websocket は明示的に閉じられる
    class _ClosingWebSocket(_MockWebSocket):
        def __init__(self, messages: list[str]) -> None:
            super().__init__(messages)
            self.close_called = False

        async def close(self) -> None:
            self.close_called = True

    async def failing_handler(
        _peer_id: str, _msg_type: MessageType, _payload: dict
    ) -> None:
        raise RuntimeError("handler error")

    ws = _ClosingWebSocket([encode_message(MessageType.PING, {})])
    peer = PeerConnection("peer-7", ws, failing_handler, require_auth=False)
    await peer.listen()

    assert ws.close_called is True
    assert peer.closed

@pytest.mark.asyncio
async def test_listen_closes_websocket_on_unexpected_receive_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Given: 受信ループで OSError が発生する
    # When: listen を実行する
    # Then: 例外は漏れず、websocket は明示的に閉じられ、エラーログが記録される
    class _ErroringWebSocket(_MockWebSocket):
        def __init__(self) -> None:
            super().__init__([])
            self.close_called = False

        async def close(self) -> None:
            self.close_called = True

    async def on_message(
        _peer_id: str, _msg_type: MessageType, _payload: dict
    ) -> None:
        return None

    ws = _ErroringWebSocket()
    ws._raise_on_iter = OSError("connection reset")
    peer = PeerConnection("peer-8", ws, on_message, require_auth=False)
    with caplog.at_level(
        logging.WARNING, logger="useful_blockchain.network.peer"
    ):
        await peer.listen()

    assert ws.close_called is True
    assert peer.closed
    assert any(
        "Unexpected error in listen loop" in record.message
        for record in caplog.records
    )

@pytest.mark.asyncio
async def test_listen_swallows_on_closed_callback_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Given: on_closed コールバックが例外を送出する
    # When: listen を実行する
    # Then: 例外は漏れず、エラーログが記録される
    async def on_message(
        _peer_id: str, _msg_type: MessageType, _payload: dict
    ) -> None:
        return None

    async def on_closed(_peer_id: str) -> None:
        raise RuntimeError("cleanup failed")

    ws = _MockWebSocket([])
    peer = PeerConnection(
        "peer-9", ws, on_message, require_auth=False, on_closed=on_closed
    )
    with caplog.at_level(logging.ERROR, logger="useful_blockchain.network.peer"):
        await peer.listen()

    assert peer.closed
    assert any(
        "on_closed callback failed" in record.message for record in caplog.records
    )

@pytest.mark.asyncio
async def test_record_listen_exception_logs_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Given: 例外で終了した listen タスク
    # When: _record_listen_exception を呼ぶ
    # Then: トレースバック付きで warning ログが記録される
    async def _run() -> None:
        raise OSError("boom")

    async def on_message(
        _peer_id: str, _msg_type: MessageType, _payload: dict
    ) -> None:
        return None

    peer = PeerConnection(
        "peer-10", _MockWebSocket([]), on_message, require_auth=False
    )
    task = asyncio.create_task(_run())
    with pytest.raises(OSError):
        # 例外を回収して un-raised 警告を防ぐ
        await task
    with caplog.at_level(logging.WARNING, logger="useful_blockchain.network.peer"):
        peer._record_listen_exception(task)

    assert any(
        "Listen task failed" in record.message and record.exc_info is not None
        for record in caplog.records
    )


def test_payload_too_big_constructor_accepts_size_and_max_size() -> None:
    # Given: ペイロードサイズと上限
    # When: PayloadTooBig を 2 つの位置引数で生成する
    # Then: TypeError にはならず、両方の値が例外に保持される
    # （websockets 12.0 / 15.0.1 / 16.1.1 / 17.2 で検証済み）
    exc = PayloadTooBig(1024, 512)
    assert exc.args == (1024, 512)
