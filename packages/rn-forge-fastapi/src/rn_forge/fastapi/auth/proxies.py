"""Which peers may speak for a client."""

from __future__ import annotations

import ipaddress
from collections.abc import Collection

__all__ = ["TrustedProxies"]


class TrustedProxies:
    """Peer addresses or CIDR networks whose forwarded headers are believed.

    Args:
        proxies: Addresses or CIDR networks, such as ``10.0.0.0/8``.
    """

    def __init__(self, proxies: Collection[str] = ()) -> None:
        self._networks = tuple(
            ipaddress.ip_network(proxy, strict=False) for proxy in proxies
        )

    def trusts(self, peer: str | None) -> bool:
        """Whether *peer* is one of the proxies."""
        if peer is None:
            return False
        try:
            address = ipaddress.ip_address(peer.strip())
        except ValueError:
            return False
        return any(address in network for network in self._networks)

    def client(self, peer: str | None, forwarded_for: Collection[str]) -> str:
        """The address of the client behind *peer*.

        Args:
            peer: The address of the connection's peer.
            forwarded_for: The ``X-Forwarded-For`` header values, in order.

        Returns:
            *peer* unless it is a trusted proxy; then the nearest address in
            the forwarded chain that is not itself a trusted proxy.
        """
        if not self.trusts(peer):
            return peer or ""
        chain = [
            hop.strip()
            for value in forwarded_for
            for hop in value.split(",")
            if hop.strip()
        ]
        for hop in reversed(chain):
            if not self.trusts(hop):
                return hop
        return peer or ""
