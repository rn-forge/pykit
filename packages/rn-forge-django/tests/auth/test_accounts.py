from __future__ import annotations

from typing import Any

import pytest

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import IntegrityError, transaction  # noqa: E402
from rn_forge.auth import (  # noqa: E402
    AccountRejected,
    AuthorizationContextCache,
    ExternalIdentity,
)
from rn_forge.django.auth.accounts import (  # noqa: E402
    DjangoAccountResolver,
    DjangoAccountStateWriter,
    ProviderPolicy,
)
from rn_forge.django.auth.authorization import (  # noqa: E402
    DjangoAuthorizationContextProvider,
    connect_authorization_signals,
)
from rn_forge.django.auth.models import ExternalAccount  # noqa: E402

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

User = get_user_model()
ISS = "https://idp.example.com"


def _identity(subject: str = "s1", **kwargs) -> ExternalIdentity:
    return ExternalIdentity(provider="p", issuer=ISS, subject=subject, **kwargs)


def _resolver(**policy) -> DjangoAccountResolver:
    return DjangoAccountResolver({"p": ProviderPolicy(**policy)})


def test_existing_policy_rejects_unlinked_identity_and_resolves_linked_one() -> None:
    resolver = _resolver()
    with pytest.raises(AccountRejected):
        resolver.resolve(_identity())
    user = User.objects.create_user("ada")
    resolver.link(ISS, "s1", user)
    assert resolver.resolve(_identity()) == str(user.pk)
    assert resolver.lookup(ISS, "s1") == str(user.pk)
    assert resolver.lookup(ISS, "other") is None
    assert resolver.lookup("https://other", "s1") is None


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(AccountRejected):
        DjangoAccountResolver({}).resolve(_identity())


def test_jit_provisions_once_and_stores_only_a_verified_email() -> None:
    resolver = _resolver(provisioning="jit")
    first = resolver.resolve(_identity(email="a@x.com", email_verified=True))
    assert resolver.resolve(_identity(email="a@x.com", email_verified=True)) == first
    assert User.objects.get(pk=first).email == "a@x.com"
    assert not User.objects.get(pk=first).has_usable_password()
    unverified = resolver.resolve(_identity("s2", email="b@x.com"))
    assert User.objects.get(pk=unverified).email == ""


def test_jit_domain_allowlist() -> None:
    resolver = _resolver(provisioning="jit", email_domains=frozenset({"corp.com"}))
    assert resolver.resolve(_identity(email="a@Corp.com", email_verified=True))
    for identity in (
        _identity("s2", email="a@corp.com"),
        _identity("s3", email="a@evil.com", email_verified=True),
        _identity("s4"),
    ):
        with pytest.raises(AccountRejected):
            resolver.resolve(identity)


def test_email_links_only_when_verified_and_domain_is_authoritative() -> None:
    user = User.objects.create_user("ada", email="Ada@corp.com")
    resolver = _resolver(authoritative_domains=frozenset({"corp.com"}))
    with pytest.raises(AccountRejected):
        resolver.resolve(_identity(email="ada@corp.com"))
    other = _resolver()
    with pytest.raises(AccountRejected):
        other.resolve(_identity(email="ada@corp.com", email_verified=True))

    assert resolver.resolve(
        _identity(email="ada@corp.com", email_verified=True)
    ) == str(user.pk)
    assert ExternalAccount.objects.get(issuer=ISS, subject="s1").user == user


def test_ambiguous_email_is_rejected() -> None:
    User.objects.create_user("a", email="x@corp.com")
    User.objects.create_user("b", email="X@corp.com")
    resolver = _resolver(authoritative_domains=frozenset({"corp.com"}))
    with pytest.raises(AccountRejected):
        resolver.resolve(_identity(email="x@corp.com", email_verified=True))


def test_sync_hook_runs_on_every_login() -> None:
    seen: list[str] = []

    def sync(user, identity) -> None:
        user.first_name = identity.name or ""
        user.save()
        seen.append(identity.subject)

    resolver = DjangoAccountResolver(
        {"p": ProviderPolicy(provisioning="jit")}, sync=sync
    )
    account = resolver.resolve(_identity(name="Ada"))
    resolver.resolve(_identity(name="Ada L"))
    assert seen == ["s1", "s1"]
    assert User.objects.get(pk=account).first_name == "Ada L"


def test_link_is_unique_on_issuer_and_subject() -> None:
    resolver = _resolver()
    resolver.link(ISS, "svc", User.objects.create_user("svc"), provider="service")
    with pytest.raises(IntegrityError), transaction.atomic():
        resolver.link(ISS, "svc", User.objects.create_user("svc2"))


def test_state_writer_drives_session_version_and_activity_through_the_cache() -> None:
    user = User.objects.create_user("ada")
    cache = AuthorizationContextCache(
        DjangoAuthorizationContextProvider(), writer=DjangoAccountStateWriter()
    )
    disconnect = connect_authorization_signals(cache)
    try:
        account = str(user.pk)
        assert cache.resolve(account).session_version == 0
        assert cache.bump_session_version(account) == 1
        assert cache.bump_session_version(account) == 2
        assert cache.resolve(account).session_version == 2
        cache.set_active(account, False)
        assert not cache.resolve(account).active
    finally:
        disconnect()


def _events(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("audit event=")
    ]


def test_jit_provisioning_is_audited_without_the_email(
    caplog: pytest.LogCaptureFixture,
    django_capture_on_commit_callbacks: Any,
) -> None:
    caplog.set_level("INFO")
    with django_capture_on_commit_callbacks(execute=True):
        account = _resolver(provisioning="jit").resolve(
            _identity(email="a@x.com", email_verified=True)
        )

    assert _events(caplog) == [
        f"audit event=account.provisioned account_id='{account}' provider='p'"
    ]


def test_disabling_an_account_is_audited(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    user = User.objects.create_user("ada")
    writer = DjangoAccountStateWriter()

    writer.set_active(str(user.pk), True)
    writer.set_active(str(user.pk), False)

    assert _events(caplog) == [f"audit event=account.disabled account_id='{user.pk}'"]
