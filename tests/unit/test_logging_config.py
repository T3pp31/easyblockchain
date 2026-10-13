import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from useful_blockchain.observability.logging_config import JsonFormatter, configure_logging


@pytest.fixture
def tokyo_tz():
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is required")
    old_tz = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Tokyo"
    time.tzset()
    # tzdata 未導入環境では TZ=Asia/Tokyo が無視され UTC 扱いになるため、
    # テストの前提が崩れて偽陰性になる。事前に反映を確認し、未反映なら skip する。
    if datetime.now().astimezone().utcoffset() != timedelta(hours=9):
        pytest.skip("TZ=Asia/Tokyo is not effective in this environment")
    yield
    if old_tz is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old_tz
    time.tzset()


def test_configure_logging_text_uses_utc_timestamp(tokyo_tz):
    # Given: TZ=Asia/Tokyo の環境
    # When: text 形式でログを出力する
    # Then: asctime は UTC で出力される
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    try:
        configure_logging(logging.INFO, log_format="text")
        before = datetime.now(timezone.utc) - timedelta(seconds=2)
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello utc text",
            args=(),
            exc_info=None,
        )
        record.created = datetime.now(timezone.utc).timestamp()
        # configure_logging は既存ハンドラを置き換えるため、Formatter を持つ
        # ハンドラから対象を特定する（インデックスに依存しない）
        handler = next(h for h in root.handlers if h.formatter is not None)
        asctime = handler.formatter.formatTime(record)
        after = datetime.now(timezone.utc)
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)

    # formatTime のミリ秒は strptime の %f（マイクロ秒）と解釈がずれるため、秒精度でパースする
    parsed = datetime.strptime(asctime.split(",")[0], "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    assert before.timestamp() <= parsed.timestamp() <= after.timestamp()


def test_configure_logging_text_format(capsys):
    # Given: text 形式のログ設定
    # When: configure_logging を呼び出してログを出力する
    # Then: プレーンテキスト形式でメッセージが出力される
    configure_logging(logging.INFO, log_format="text")
    logging.getLogger("test.logger").info("hello text")
    captured = capsys.readouterr()
    assert "hello text" in captured.err
    assert "INFO" in captured.err


def test_configure_logging_json_format(capsys):
    # Given: JSON 形式のログ設定
    # When: configure_logging を呼び出してログを出力する
    # Then: JSON 形式でメッセージが出力される
    configure_logging(logging.INFO, log_format="json", node_id="node-1")
    logging.getLogger("test.logger").info("hello json")
    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip())
    assert payload["message"] == "hello json"
    assert payload["level"] == "INFO"
    assert payload["node_id"] == "node-1"


def test_configure_logging_accepts_validated_format(capsys):
    # Given: settings で検証済みのログ形式
    # When: configure_logging を呼び出してログを出力する
    # Then: 指定形式で出力される
    configure_logging(logging.INFO, log_format="json", node_id="node-1")
    logging.getLogger("test.logger").info("validated format")
    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip())
    assert payload["message"] == "validated format"


def test_json_formatter_includes_extra_fields():
    # Given: peer_id を含むログレコード
    # When: JsonFormatter で整形する
    # Then: 追加フィールドが JSON に含まれる
    formatter = JsonFormatter(node_id="node-abc")
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="peer event",
        args=(),
        exc_info=None,
    )
    record.peer_id = "peer-1"
    payload = json.loads(formatter.format(record))
    assert payload["peer_id"] == "peer-1"
    assert payload["node_id"] == "node-abc"
