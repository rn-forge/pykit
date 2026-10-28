"""The trusted-proxy rule shared by the CSRF origin check and the rate limits."""

import pytest
from rn_forge.fastapi.auth.proxies import TrustedProxies

pytestmark = pytest.mark.unit

PROXIES = TrustedProxies(["10.0.0.0/8", "192.168.1.1"])


@pytest.mark.parametrize(
    ("peer", "trusted"),
    [
        ("10.1.2.3", True),
        ("192.168.1.1", True),
        ("192.168.1.2", False),
        ("203.0.113.9", False),
        ("testclient", False),
        (None, False),
    ],
)
def test_a_peer_is_trusted_when_it_is_in_a_listed_network(peer, trusted):
    assert PROXIES.trusts(peer) is trusted


@pytest.mark.parametrize(
    ("peer", "forwarded", "client"),
    [
        ("203.0.113.9", ["1.1.1.1"], "203.0.113.9"),
        ("10.0.0.1", [], "10.0.0.1"),
        ("10.0.0.1", ["1.1.1.1"], "1.1.1.1"),
        ("10.0.0.1", ["9.9.9.9, 1.1.1.1"], "1.1.1.1"),
        ("10.0.0.1", ["9.9.9.9", "1.1.1.1, 10.0.0.2"], "1.1.1.1"),
        ("10.0.0.1", ["10.0.0.7"], "10.0.0.1"),
        ("10.0.0.1", ["garbage"], "garbage"),
        (None, ["1.1.1.1"], ""),
    ],
)
def test_the_client_is_the_nearest_untrusted_hop_behind_a_trusted_peer(
    peer, forwarded, client
):
    assert PROXIES.client(peer, forwarded) == client
