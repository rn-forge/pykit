"""Tests for rn_forge.auth.context_cache."""

from datetime import timedelta

import pytest

from rn_forge.auth import (
    AuthorizationContext,
    AuthorizationContextCache,
    AuthorizationContextProvider,
    InMemoryAuthorizationVersions,
)

pytestmark = pytest.mark.unit


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Store:
    """Provider and writer over one dict, counting resolves."""

    def __init__(self) -> None:
        self.active: dict[str, bool] = {}
        self.session: dict[str, int] = {}
        self.calls = 0

    def resolve(self, account_id: str) -> AuthorizationContext:
        self.calls += 1
        return AuthorizationContext(
            active=self.active.get(account_id, True),
            session_version=self.session.get(account_id, 1),
        )

    def set_active(self, account_id: str, active: bool) -> None:
        self.active[account_id] = active

    def bump_session_version(self, account_id: str) -> int:
        self.session[account_id] = self.session.get(account_id, 1) + 1
        return self.session[account_id]


def make(
    writer: bool = True, ttl: timedelta = timedelta(seconds=60)
) -> tuple[AuthorizationContextCache, Store, Clock]:
    store, clock = Store(), Clock()
    cache = AuthorizationContextCache(
        store, ttl=ttl, writer=store if writer else None, clock=clock
    )
    return cache, store, clock


def test_hit_at_same_version():
    cache, store, _ = make()
    assert cache.resolve("a") is cache.resolve("a")
    assert store.calls == 1


def test_invalidate_misses_only_that_account():
    cache, store, _ = make()
    cache.resolve("a")
    cache.resolve("b")
    cache.invalidate("a")
    cache.resolve("a")
    cache.resolve("b")
    assert store.calls == 3


def test_invalidate_all_misses_every_account():
    cache, store, _ = make()
    cache.resolve("a")
    cache.resolve("b")
    cache.invalidate_all()
    cache.resolve("a")
    cache.resolve("b")
    assert store.calls == 4


def test_change_without_the_api_applies_after_ttl():
    cache, store, clock = make(ttl=timedelta(seconds=10))
    assert cache.resolve("a").active is True
    store.active["a"] = False
    clock.now = 9.9
    assert cache.resolve("a").active is True
    clock.now = 10.0
    assert cache.resolve("a").active is False


def test_set_active_is_seen_by_next_resolve():
    cache, _, _ = make()
    assert cache.resolve("a").active is True
    cache.set_active("a", False)
    assert cache.resolve("a").active is False


def test_bump_session_version_is_seen_by_next_resolve():
    cache, _, _ = make()
    assert cache.resolve("a").session_version == 1
    assert cache.bump_session_version("a") == 2
    assert cache.resolve("a").session_version == 2


def test_writes_without_a_writer_raise():
    cache, _, _ = make(writer=False)
    with pytest.raises(RuntimeError):
        cache.set_active("a", False)
    with pytest.raises(RuntimeError):
        cache.bump_session_version("a")


@pytest.mark.parametrize("ttl", [timedelta(0), timedelta(seconds=-1)])
def test_non_positive_ttl_raises(ttl: timedelta):
    with pytest.raises(ValueError):
        make(ttl=ttl)


def test_cache_is_a_provider():
    cache, _, _ = make()
    assert isinstance(cache, AuthorizationContextProvider)


def test_shared_versions_invalidate_across_caches():
    versions = InMemoryAuthorizationVersions()
    store = Store()
    one = AuthorizationContextCache(store, versions=versions)
    two = AuthorizationContextCache(store, versions=versions)
    one.resolve("a")
    two.resolve("a")
    one.invalidate("a")
    two.resolve("a")
    assert store.calls == 3
