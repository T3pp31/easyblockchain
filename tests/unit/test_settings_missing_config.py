from pathlib import Path

import pytest

from useful_blockchain import settings


@pytest.mark.parametrize("source", ["argument", "environment"])
def test_explicit_missing_config_raises(tmp_path, monkeypatch, source):
    # Given: 明示的に指定された存在しない設定ファイル
    path = tmp_path / "missing.yaml"
    monkeypatch.delenv("EASYBLOCKCHAIN_CONFIG", raising=False)
    kwargs = {}
    if source == "argument":
        kwargs["config_path"] = path
    else:
        monkeypatch.setenv("EASYBLOCKCHAIN_CONFIG", str(path))
    # When: 上書き付きで設定を読む
    # Then: 安全でない既定値起動を避け、パス付きエラーを返す
    with pytest.raises(FileNotFoundError, match="Config file not found") as exc:
        settings.load_settings_with_overrides(**kwargs, overrides={"network": {"port": 0}})
    assert str(path) in str(exc.value)


def test_missing_implicit_default_still_supports_overrides(tmp_path, monkeypatch):
    # Given: パッケージの既定設定ファイルが配置されていない環境
    monkeypatch.delenv("EASYBLOCKCHAIN_CONFIG", raising=False)
    monkeypatch.setattr(settings, "DEFAULT_CONFIG_PATH", tmp_path / "absent.yaml")
    # When: 明示パスなしで上書き設定を読む
    loaded = settings.load_settings_with_overrides(overrides={"network": {"port": 0}})
    # Then: 既存のパッケージ利用時の挙動を維持する
    assert loaded.network.port == 0


def test_argument_config_takes_precedence_over_environment(tmp_path, monkeypatch):
    # Given: 間違った環境変数と有効な引数パス
    path = tmp_path / "config.yaml"
    path.write_text("network:\n  port: 1234\n")
    monkeypatch.setenv("EASYBLOCKCHAIN_CONFIG", str(tmp_path / "absent.yaml"))
    # When: 引数の設定ファイルを指定する
    loaded = settings.load_settings_with_overrides(config_path=Path(path))
    # Then: 引数側が適用される
    assert loaded.network.port == 1234


@pytest.mark.parametrize("name", [
    "chain_sync_max_blocks", "chain_sync_max_bytes", "mdns_max_pending_services",
    "mdns_resolution_timeout_seconds", "mdns_resolution_interval_seconds",
])
@pytest.mark.parametrize("value", [0, -1, None, "invalid", float("inf"), float("nan")])
def test_network_limits_reject_invalid_values(name, value):
    # Given: 上限設定の境界・非有限・不正入力
    # When: 設定を解析する
    # Then: 問題の項目名を含むエラーを返す
    with pytest.raises(ValueError, match=f"network.{name} must be a finite positive number"):
        settings.parse_settings({"network": {name: value}})
