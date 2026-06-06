import pytest

from useful_blockchain.network.messages import MessageType, decode_message, encode_message


def test_encode_decode_roundtrip():
    raw = encode_message(MessageType.HELLO, {"node_id": "n1", "chain_height": 0})
    msg_type, payload = decode_message(raw)
    assert msg_type == MessageType.HELLO
    assert payload["node_id"] == "n1"
    assert payload["chain_height"] == 0


def test_decode_invalid_message():
    with pytest.raises(ValueError):
        decode_message('{"foo": "bar"}')
