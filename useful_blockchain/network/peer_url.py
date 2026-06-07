"""ピア接続 URL の検証。"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass
from urllib.parse import ParseResult, urlparse

from useful_blockchain.network.tls import rejects_plain_websocket, url_scheme_matches_tls
from useful_blockchain.types import Environment, NetworkSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PeerConnectTarget:
    """接続直前に解決・検証されたピア接続先。"""

    url: str
    host: str
    port: int
    hostname: str


def _parse_blocked_networks(
    blocked_cidrs: list[str],
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for cidr in blocked_cidrs:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid blocked CIDR: %s", cidr)
    return networks


def _resolve_host_ips(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        addr_info = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        logger.warning("Failed to resolve peer hostname %s: %s", hostname, exc)
        return []
    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for family, _, _, _, sockaddr in addr_info:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        host = str(sockaddr[0])
        if host in seen:
            continue
        seen.add(host)
        try:
            ips.append(ipaddress.ip_address(host))
        except ValueError:
            logger.warning("Invalid resolved peer IP for %s: %s", hostname, host)
    return ips


_METADATA_IP = ipaddress.ip_address("169.254.169.254")


def _is_restricted_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_private_ips: bool,
    blocked_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> bool:
    if ip == _METADATA_IP:
        return True
    if allow_private_ips:
        return False
    for network in blocked_networks:
        if ip in network:
            return True
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


def _default_port_for_scheme(scheme: str) -> int:
    return 443 if scheme == "wss" else 80


def _parse_peer_url(
    url: str,
    settings: NetworkSettings,
    environment: Environment,
) -> ParseResult | None:
    if not url:
        return None

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("ws", "wss"):
        logger.warning("Rejected peer URL with invalid scheme: %s", url)
        return None

    if scheme == "ws" and rejects_plain_websocket(settings.tls.enabled, environment):
        logger.warning("Rejected plain WebSocket peer URL: %s", url)
        return None

    if not url_scheme_matches_tls(url, settings.tls.enabled):
        logger.warning("Rejected peer URL with TLS scheme mismatch: %s", url)
        return None

    if not parsed.hostname:
        logger.warning("Rejected peer URL without hostname: %s", url)
        return None

    if parsed.username or parsed.password:
        logger.warning("Rejected peer URL with userinfo: %s", url)
        return None

    if parsed.fragment:
        logger.warning("Rejected peer URL with fragment: %s", url)
        return None

    if parsed.path not in ("", "/"):
        logger.warning("Rejected peer URL with non-root path: %s", url)
        return None

    return parsed


def _resolve_peer_ips(
    hostname: str,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        literal_ip = ipaddress.ip_address(hostname)
        return [literal_ip]
    except ValueError:
        return _resolve_host_ips(hostname)


def _peer_ips_allowed(
    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address],
    settings: NetworkSettings,
    url: str,
) -> bool:
    if not ips:
        logger.warning("Rejected peer URL with unresolvable hostname: %s", url)
        return False

    blocked_networks = _parse_blocked_networks(settings.peer_connect.blocked_cidrs)
    peer_connect = settings.peer_connect

    for ip in ips:
        if _is_restricted_ip(
            ip,
            allow_private_ips=peer_connect.allow_private_ips,
            blocked_networks=blocked_networks,
        ):
            logger.warning("Rejected peer URL targeting restricted IP %s: %s", ip, url)
            return False

    return True


def validate_peer_url(
    url: str,
    settings: NetworkSettings,
    environment: Environment,
) -> str | None:
    """ピア URL を検証し、許可される場合は URL を返す。"""
    parsed = _parse_peer_url(url, settings, environment)
    if parsed is None:
        return None

    hostname = parsed.hostname
    if hostname is None:
        return None

    ips = _resolve_peer_ips(hostname)
    if not _peer_ips_allowed(ips, settings, url):
        return None

    return url


def resolve_peer_connect_target(
    url: str,
    settings: NetworkSettings,
    environment: Environment,
) -> PeerConnectTarget | None:
    """接続直前に DNS 解決・IP 検証を行い、ピンされた接続先を返す。"""
    parsed = _parse_peer_url(url, settings, environment)
    if parsed is None:
        return None

    hostname = parsed.hostname
    if hostname is None:
        return None

    ips = _resolve_peer_ips(hostname)
    if not _peer_ips_allowed(ips, settings, url):
        return None

    port = parsed.port if parsed.port is not None else _default_port_for_scheme(parsed.scheme)
    return PeerConnectTarget(
        url=url,
        host=str(ips[0]),
        port=port,
        hostname=hostname,
    )
