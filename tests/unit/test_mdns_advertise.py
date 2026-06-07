"""mDNS advertise のユニットテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from useful_blockchain.network.discovery import (
    PeerDiscovery,
    build_mdns_instance_name,
    resolve_advertise_host,
)
from useful_blockchain.types import NetworkSettings


@pytest.fixture
def mdns_settings() -> NetworkSettings:
    return NetworkSettings(
        mdns_enabled=True,
        mdns_advertise_enabled=True,
        mdns_advertise_host="192.168.1.10",
        mdns_instance_name="test-node",
        mdns_service_name="_easyblockchain._tcp.local.",
    )


def test_resolve_advertise_host_explicit(mdns_settings: NetworkSettings) -> None:
    # Given: mdns_advertise_host が設定されている
    # When: resolve_advertise_host を呼ぶ
    # Then: 設定値が返る
    assert resolve_advertise_host(mdns_settings) == "192.168.1.10"


def test_resolve_advertise_host_from_bind_host() -> None:
    # Given: 固定 host が設定されている
    # When: resolve_advertise_host を呼ぶ
    # Then: bind host が返る
    settings = NetworkSettings(host="10.0.0.5", mdns_advertise_host="")
    assert resolve_advertise_host(settings) == "10.0.0.5"


@patch("useful_blockchain.network.discovery.socket.socket")
def test_resolve_advertise_host_auto_detect(mock_socket_ctor: MagicMock) -> None:
    # Given: 0.0.0.0 バインドで自動検出
    # When: resolve_advertise_host を呼ぶ
    # Then: UDP ソケットで取得した IP が返る
    mock_sock = MagicMock()
    mock_sock.getsockname.return_value = ("172.16.0.2", 0)
    mock_socket_ctor.return_value.__enter__.return_value = mock_sock
    settings = NetworkSettings(host="0.0.0.0", mdns_advertise_host="")
    assert resolve_advertise_host(settings) == "172.16.0.2"


@patch("useful_blockchain.network.discovery.socket.socket")
def test_resolve_advertise_host_auto_detect_failure(mock_socket_ctor: MagicMock) -> None:
    # Given: 自動検出が失敗する
    # When: resolve_advertise_host を呼ぶ
    # Then: 127.0.0.1 にフォールバック
    mock_socket_ctor.side_effect = OSError("no route")
    settings = NetworkSettings(host="0.0.0.0", mdns_advertise_host="")
    assert resolve_advertise_host(settings) == "127.0.0.1"


def test_build_mdns_instance_name_from_settings(mdns_settings: NetworkSettings) -> None:
    # Given: mdns_instance_name が設定されている
    # When: build_mdns_instance_name を呼ぶ
    # Then: 設定値が返る
    assert build_mdns_instance_name(mdns_settings, "node-abc") == "test-node"


def test_build_mdns_instance_name_from_node_id() -> None:
    # Given: mdns_instance_name が空
    # When: build_mdns_instance_name を呼ぶ
    # Then: node_id 先頭8文字から生成される
    settings = NetworkSettings(mdns_instance_name="")
    assert build_mdns_instance_name(settings, "12345678-abcd") == "easyblockchain-12345678"


def test_start_mdns_disabled_is_noop() -> None:
    # Given: mdns_enabled が false
    # When: start_mdns を呼ぶ
    # Then: zeroconf は起動しない
    discovery = PeerDiscovery(NetworkSettings(mdns_enabled=False), "ws://127.0.0.1:8765")
    with patch("zeroconf.Zeroconf") as mock_zc:
        discovery.start_mdns(port=8765, node_id="n1")
        mock_zc.assert_not_called()


@patch("useful_blockchain.network.discovery.PeerDiscovery._register_advertise")
def test_start_mdns_browse_only_when_advertise_disabled(
    mock_register: MagicMock,
    mdns_settings: NetworkSettings,
) -> None:
    # Given: advertise が無効
    # When: start_mdns を呼ぶ
    # Then: browse のみで register は呼ばれない
    mdns_settings.mdns_advertise_enabled = False
    discovery = PeerDiscovery(mdns_settings, "ws://127.0.0.1:8765")
    mock_zc = MagicMock()
    with patch("zeroconf.Zeroconf", return_value=mock_zc), patch(
        "zeroconf.ServiceBrowser"
    ):
        discovery.start_mdns(port=8765, node_id="n1")
    mock_register.assert_not_called()
    discovery.stop_mdns()


@patch("useful_blockchain.network.discovery.PeerDiscovery._register_advertise")
def test_start_mdns_registers_when_advertise_enabled(
    mock_register: MagicMock,
    mdns_settings: NetworkSettings,
) -> None:
    # Given: advertise が有効
    # When: start_mdns を呼ぶ
    # Then: register が呼ばれる
    discovery = PeerDiscovery(mdns_settings, "ws://127.0.0.1:8765")
    with patch("zeroconf.Zeroconf"), patch("zeroconf.ServiceBrowser"):
        discovery.start_mdns(port=8765, node_id="n1", properties={"node_id": "n1"})
    mock_register.assert_called_once()


def test_register_advertise_creates_service_info(mdns_settings: NetworkSettings) -> None:
    # Given: zeroconf が起動済み
    # When: _register_advertise を呼ぶ
    # Then: ServiceInfo が登録される
    discovery = PeerDiscovery(mdns_settings, "ws://127.0.0.1:8765")
    mock_zc = MagicMock()
    discovery._zeroconf = mock_zc  # noqa: SLF001
    mock_service_info = MagicMock()
    with patch("zeroconf.ServiceInfo", return_value=mock_service_info) as mock_info_cls:
        discovery._register_advertise(  # noqa: SLF001
            ServiceInfo=mock_info_cls,
            port=9999,
            node_id="node-1",
            properties={"consensus_type": "pow"},
        )
    mock_info_cls.assert_called_once()
    mock_zc.register_service.assert_called_once_with(mock_service_info)
    assert discovery._service_info is mock_service_info  # noqa: SLF001


def test_register_advertise_skips_invalid_host(mdns_settings: NetworkSettings) -> None:
    # Given: 不正な advertise host
    # When: _register_advertise を呼ぶ
    # Then: 登録されない
    mdns_settings.mdns_advertise_host = "not-an-ip"
    discovery = PeerDiscovery(mdns_settings, "ws://127.0.0.1:8765")
    mock_zc = MagicMock()
    discovery._zeroconf = mock_zc  # noqa: SLF001
    with patch("zeroconf.ServiceInfo") as mock_info_cls:
        discovery._register_advertise(  # noqa: SLF001
            ServiceInfo=mock_info_cls,
            port=8765,
            node_id="node-1",
            properties={},
        )
    mock_info_cls.assert_not_called()
    mock_zc.register_service.assert_not_called()


def test_stop_mdns_unregisters_and_closes(mdns_settings: NetworkSettings) -> None:
    # Given: browse + advertise 起動済み
    # When: stop_mdns を呼ぶ
    # Then: unregister, browser cancel, close が呼ばれる
    discovery = PeerDiscovery(mdns_settings, "ws://127.0.0.1:8765")
    mock_zc = MagicMock()
    mock_browser = MagicMock()
    mock_info = MagicMock()
    discovery._zeroconf = mock_zc  # noqa: SLF001
    discovery._browser = mock_browser  # noqa: SLF001
    discovery._service_info = mock_info  # noqa: SLF001
    discovery.stop_mdns()
    mock_zc.unregister_service.assert_called_once_with(mock_info)
    mock_browser.cancel.assert_called_once()
    mock_zc.close.assert_called_once()
    assert discovery._zeroconf is None  # noqa: SLF001


def test_start_mdns_import_error_is_noop(mdns_settings: NetworkSettings) -> None:
    # Given: zeroconf が未インストール
    # When: start_mdns を呼ぶ
    # Then: 例外なく終了する
    discovery = PeerDiscovery(mdns_settings, "ws://127.0.0.1:8765")
    with patch.dict("sys.modules", {"zeroconf": None}):
        discovery.start_mdns(port=8765, node_id="n1")
