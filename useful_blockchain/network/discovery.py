"""ピア発見（ブートストラップ + mDNS）。"""

from __future__ import annotations

import logging
import socket
from typing import TYPE_CHECKING, Any, Callable

from useful_blockchain.types import NetworkSettings

if TYPE_CHECKING:
    from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf

logger = logging.getLogger(__name__)


def resolve_advertise_host(settings: NetworkSettings) -> str:
    """mDNS advertise 用の LAN IPv4 を解決する。"""
    if settings.mdns_advertise_host:
        return settings.mdns_advertise_host
    if settings.host not in ("0.0.0.0", ""):
        return settings.host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"


def build_mdns_instance_name(settings: NetworkSettings, node_id: str) -> str:
    if settings.mdns_instance_name:
        return settings.mdns_instance_name
    short_id = node_id[:8] if len(node_id) >= 8 else node_id
    return f"easyblockchain-{short_id}"


class PeerDiscovery:
    def __init__(self, settings: NetworkSettings, local_url: str) -> None:
        self.settings = settings
        self.local_url = local_url
        self._known_peers: set[str] = set(settings.bootstrap_peers)
        self._zeroconf: Zeroconf | None = None
        self._browser: ServiceBrowser | None = None
        self._service_info: ServiceInfo | None = None

    @property
    def known_peers(self) -> list[str]:
        peers = sorted(self._known_peers)
        return [p for p in peers if p != self.local_url]

    def add_peer(self, url: str) -> None:
        if url and url != self.local_url:
            self._known_peers.add(url)

    def add_peers(self, urls: list[str]) -> None:
        for url in urls:
            self.add_peer(url)

    def start_mdns(
        self,
        *,
        port: int,
        node_id: str,
        on_peer_found: Callable[[str], None] | None = None,
        properties: dict[str, str] | None = None,
    ) -> None:
        if not self.settings.mdns_enabled:
            return
        try:
            from zeroconf import ServiceBrowser, ServiceInfo, ServiceListener, Zeroconf

            class Listener(ServiceListener):
                def __init__(
                    self,
                    outer: PeerDiscovery,
                    callback: Callable[[str], None] | None,
                ) -> None:
                    self.outer = outer
                    self.callback = callback

                def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    info = zc.get_service_info(type_, name)
                    if info and info.addresses:
                        host = socket.inet_ntoa(info.addresses[0])
                        from useful_blockchain.network.tls import websocket_scheme

                        scheme = websocket_scheme(self.outer.settings.tls.enabled)
                        url = f"{scheme}://{host}:{info.port}"
                        self.outer.add_peer(url)
                        if self.callback:
                            self.callback(url)

                def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    pass

                def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    pass

            self._zeroconf = Zeroconf()
            self._browser = ServiceBrowser(
                self._zeroconf,
                self.settings.mdns_service_name,
                Listener(self, on_peer_found),
            )
            logger.info("mDNS discovery started")

            if self.settings.mdns_advertise_enabled:
                self._register_advertise(
                    ServiceInfo=ServiceInfo,
                    port=port,
                    node_id=node_id,
                    properties=properties or {},
                )
        except ImportError:
            logger.warning("zeroconf not installed; mDNS discovery disabled")

    def _register_advertise(
        self,
        *,
        ServiceInfo: type[ServiceInfo],
        port: int,
        node_id: str,
        properties: dict[str, str],
    ) -> None:
        if self._zeroconf is None:
            return
        host = resolve_advertise_host(self.settings)
        instance_name = build_mdns_instance_name(self.settings, node_id)
        service_type = self.settings.mdns_service_name
        service_name = f"{instance_name}.{service_type}"
        txt_properties: dict[str, Any] = {
            key: value.encode("utf-8") for key, value in properties.items()
        }
        txt_properties.setdefault(b"node_id", node_id.encode("utf-8"))
        try:
            address = socket.inet_aton(host)
        except OSError:
            logger.warning("Invalid mDNS advertise host %s; skipping advertise", host)
            return
        self._service_info = ServiceInfo(
            type_=service_type,
            name=service_name,
            addresses=[address],
            port=port,
            properties=txt_properties,
        )
        self._zeroconf.register_service(self._service_info)
        logger.info("mDNS advertise started at %s:%s as %s", host, port, service_name)

    def stop_mdns(self) -> None:
        if self._zeroconf is None:
            return
        if self._service_info is not None:
            try:
                self._zeroconf.unregister_service(self._service_info)
            except Exception as exc:
                logger.warning("mDNS unregister failed: %s", exc)
            self._service_info = None
        if self._browser is not None:
            self._browser.cancel()
            self._browser = None
        self._zeroconf.close()
        self._zeroconf = None
