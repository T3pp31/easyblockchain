"""構造化ログの初期化。"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from useful_blockchain.types import LogFormat


class JsonFormatter(logging.Formatter):
    """JSON 形式でログレコードを出力するフォーマッタ。"""

    def __init__(self, node_id: str = "") -> None:
        super().__init__()
        self._node_id = node_id

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if self._node_id:
            payload["node_id"] = self._node_id
        for key in ("peer_id", "block_index", "event"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    level: int,
    log_format: LogFormat = "text",
    node_id: str = "",
) -> None:
    """ルートロガーを初期化する。"""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    if log_format == "json":
        handler.setFormatter(JsonFormatter(node_id=node_id))
    else:
        text_format = "%(asctime)s %(levelname)s %(name)s: %(message)s"
        handler.setFormatter(logging.Formatter(text_format))

    root.addHandler(handler)
