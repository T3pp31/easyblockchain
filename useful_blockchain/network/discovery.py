"""ピア発見（ブートストラップ + mDNS）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from useful_blockchain.network.peer_url import validate_peer_url
from useful_blockchain.types import Environment, NetworkSettings

if TYPE_CHECKING:
    from zeroconf import ServiceBrowser, Zeroconf

logger = logging.getLogger(__name__)


class PeerDiscovery:
    def __init__(
        self,
        settings: NetworkSettings,
        local_url: str,
        environment: Environment = "development",
    ) -> None:
        self.settings = settings
        self.local_url = local_url
        self._environment = environment
        self._known_peers: set[str] = set()
        for url in settings.bootstrap_peers:
            self.add_peer(url)
        self._mdns: tuple[Zeroconf, ServiceBrowser] | None = None

    @property
    def known_peers(self) -> list[str]:
        peers = sorted(self._known_peers)
        return [p for p in peers if p != self.local_url]

    def add_peer(self, url: str) -> None:
        if not url or url == self.local_url:
            return
        if validate_peer_url(url, self.settings, self._environment) is None:
            return
        self._known_peers.add(url)

    def add_peers(self, urls: list[str]) -> None:
        max_count = self.settings.peer_connect.max_peers_per_message
        if len(urls) > max_count:
            logger.warning(
                "Truncating PEERS message from %s to %s entries",
                len(urls),
                max_count,
            )
        for url in urls[:max_count]:
            self.add_peer(url)

    def start_mdns(self, on_peer_found: Callable[[str], None] | None = None) -> None:
        if not self.settings.mdns_enabled:
            return
        try:
            from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

            class Listener(ServiceListener):
                def __init__(self, outer: PeerDiscovery, callback: Callable[[str], None] | None) -> None:
                    self.outer = outer
                    self.callback = callback

                def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    info = zc.get_service_info(type_, name)
                    if info and info.addresses:
                        import socket

                        host = socket.inet_ntoa(info.addresses[0])
                        port = info.port
                        from useful_blockchain.network.tls import websocket_scheme

                        scheme = websocket_scheme(self.outer.settings.tls.enabled)
                        url = f"{scheme}://{host}:{port}"
                        self.outer.add_peer(url)
                        if self.callback:
                            self.callback(url)

                def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    pass

                def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    pass

            zc = Zeroconf()
            self._mdns = (zc, ServiceBrowser(zc, self.settings.mdns_service_name, Listener(self, on_peer_found)))
            logger.info("mDNS discovery started")
        except ImportError:
            logger.warning("zeroconf not installed; mDNS discovery disabled")

    def stop_mdns(self) -> None:
        if self._mdns:
            zc, browser = self._mdns
            browser.cancel()
            zc.close()
            self._mdns = None
