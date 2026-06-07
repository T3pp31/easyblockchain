import pytest
from websockets.exceptions import PayloadTooBig

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

    async def close(self) -> None:
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
    peer = PeerConnection("peer-1", ws, on_message)
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
    peer = PeerConnection("peer-2", ws, on_message)
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
    peer = PeerConnection("peer-3", ws, on_message)
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
    peer = PeerConnection("peer-4", ws, lambda *_: None, max_message_bytes=32)
    huge_payload = {"data": "x" * 100}
    await peer.send(MessageType.HELLO, huge_payload)

    assert sent == []
