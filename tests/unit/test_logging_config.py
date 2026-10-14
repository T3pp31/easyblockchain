import json
import logging

import pytest

from useful_blockchain.observability.logging_config import JsonFormatter, configure_logging


@pytest.fixture(autouse=True)
def restore_root_logger():
    # Given: configure_logging がルートロガーをグローバルに書き換える
    # When: テストが終了する
    # Then: テスト中に追加されたハンドラを削除し、レベルを復元する
    # NOTE: スナップショット済みハンドラの再追加はしない。pytest のロギング
    # プラグインは各フェーズで root にキャプチャハンドラを追加・削除するため、
    # setup 時に取得したハンドラを teardown で再追加すると、既に削除済みの
    # フェーズハンドラが復活して蓄積する（leak）。remove-only で復元する。
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    yield
    for handler in [h for h in root.handlers if h not in handlers]:
        root.removeHandler(handler)
    root.setLevel(level)


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
