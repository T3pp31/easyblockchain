"""ピア発見（ブートストラップ + mDNS）。"""

from __future__ import annotations

import logging
import queue
import socket
import threading
from typing import TYPE_CHECKING, Any, Callable, Mapping

from useful_blockchain.network.peer_url import validate_peer_url
from useful_blockchain.types import Environment, NetworkSettings

if TYPE_CHECKING:
    from zeroconf import ServiceBrowser, Zeroconf

logger = logging.getLogger(__name__)


def _mdns_tls_enabled(properties: Mapping[Any, bytes | str | None] | None) -> bool:
    """mDNS TXT レコードの tls フラグからスキームを決定する。"""
    if not properties:
        return False
    flag = properties.get(b"tls", properties.get("tls"))
    if isinstance(flag, bytes):
        flag = flag.decode("utf-8", errors="ignore")
    return str(flag) == "1"


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
        self._known_peers_lock = threading.Lock()
        # 挿入順を保持し、上限超過時に最古のエントリを追い出す
        self._known_peers: dict[str, None] = {}
        for url in settings.bootstrap_peers:
            self.add_peer(url)
        self._mdns: tuple[Zeroconf, ServiceBrowser] | None = None
        self._mdns_stop = threading.Event()
        self._mdns_worker: threading.Thread | None = None

    @property
    def known_peers(self) -> list[str]:
        with self._known_peers_lock:
            peers = sorted(self._known_peers)
        return [p for p in peers if p != self.local_url]

    def add_peer(self, url: str) -> None:
        if not url or url == self.local_url:
            return
        if validate_peer_url(url, self.settings, self._environment) is None:
            return
        with self._known_peers_lock:
            if url in self._known_peers:
                del self._known_peers[url]
            self._known_peers[url] = None
            max_known = self.settings.peer_connect.max_known_peers
            while len(self._known_peers) > max_known:
                del self._known_peers[next(iter(self._known_peers))]

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
        if not self.settings.mdns_enabled or self._mdns is not None:
            return
        zc = None
        try:
            from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

            requests: queue.Queue[tuple[str, str]] = queue.Queue(
                maxsize=self.settings.mdns_max_pending_services
            )
            stop = threading.Event()
            self._mdns_stop = stop

            class Listener(ServiceListener):
                def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    if stop.is_set():
                        return
                    try:
                        requests.put_nowait((type_, name))
                    except queue.Full:
                        logger.debug("mDNS resolution queue full; dropping %s", name)

                def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    pass

                def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    pass

            zc = Zeroconf()
            self._mdns = (zc, ServiceBrowser(zc, self.settings.mdns_service_name, Listener()))
            worker = threading.Thread(
                target=self._resolve_mdns_services,
                args=(zc, requests, stop, on_peer_found),
                name="easyblockchain-mdns-resolver",
                daemon=True,
            )
            worker.start()
            self._mdns_worker = worker
            self._register_self(zc)
            logger.info("mDNS discovery started")
        except ImportError:
            logger.warning("zeroconf not installed; mDNS discovery disabled")
            if zc is not None:
                self._cleanup_mdns(zc)
                self.stop_mdns()
        except Exception:
            logger.warning("mDNS discovery startup failed", exc_info=True)
            if zc is not None:
                self._cleanup_mdns(zc)
                self.stop_mdns()

    def _resolve_mdns_services(
        self,
        zc: Zeroconf,
        requests: queue.Queue[tuple[str, str]],
        stop: threading.Event,
        callback: Callable[[str], None] | None,
    ) -> None:
        from useful_blockchain.network.tls import websocket_scheme

        interval = self.settings.mdns_resolution_interval_seconds
        while not stop.is_set():
            try:
                type_, name = requests.get(timeout=interval)
            except queue.Empty:
                continue
            try:
                info = zc.get_service_info(
                    type_, name,
                    timeout=int(self.settings.mdns_resolution_timeout_seconds * 1000),
                )
                if info and info.addresses and not stop.is_set():
                    host = socket.inet_ntoa(info.addresses[0])
                    scheme = websocket_scheme(_mdns_tls_enabled(info.properties))
                    url = f"{scheme}://{host}:{info.port}"
                    if validate_peer_url(url, self.settings, self._environment) is not None:
                        self.add_peer(url)
                        if callback:
                            callback(url)
            except Exception:
                logger.warning("mDNS service resolution failed for %s", name, exc_info=True)
            if stop.wait(interval):
                break

    def _register_self(self, zc: Zeroconf) -> None:
        """自ノードを mDNS で広告する（TXT に TLS フラグを含める）。"""
        from urllib.parse import urlparse

        from zeroconf import ServiceInfo

        parsed = urlparse(self.local_url)
        host = parsed.hostname or ""
        port = parsed.port
        if not host or not port:
            return
        try:
            import socket

            addresses = [socket.inet_aton(host)]
        except OSError:
            logger.warning("mDNS advertisement skipped: cannot resolve local host %s", host)
            return
        properties = {"tls": "1" if self.settings.tls.enabled else "0"}
        info = ServiceInfo(
            self.settings.mdns_service_name,
            f"easyblockchain-{host}-{port}.{self.settings.mdns_service_name}",
            addresses=addresses,
            port=port,
            properties=properties,
        )
        try:
            zc.register_service(info)
        except Exception:
            logger.warning("mDNS self-advertisement failed", exc_info=True)

    def stop_mdns(self) -> None:
        self._mdns_stop.set()
        try:
            if self._mdns:
                zc, _ = self._mdns
                self._cleanup_mdns(zc)
        finally:
            if self._mdns_worker is not None:
                self._mdns_worker.join(
                    timeout=self.settings.mdns_resolution_timeout_seconds
                    + self.settings.mdns_resolution_interval_seconds
                )
                self._mdns_worker = None

    def _cleanup_mdns(self, zc: Zeroconf) -> None:
        self._mdns_stop.set()
        if self._mdns is not None:
            zc, browser = self._mdns
            self._mdns = None
            try:
                browser.cancel()
            except Exception:
                logger.warning("mDNS browser shutdown failed", exc_info=True)
        try:
            zc.close()
        except Exception:
            logger.warning("mDNS socket shutdown failed", exc_info=True)
