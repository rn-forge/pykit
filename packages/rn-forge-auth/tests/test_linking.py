from datetime import UTC, datetime

import pytest
from rn_forge.auth.context import AuthorizationContext
from rn_forge.auth.identity import SessionInfo
from rn_forge.auth.principal import Principal


class Accounts:
    def __init__(self, account_id: str | None) -> None:
        self.account_id = account_id
        self.lookups: list[tuple[str, str]] = []

    def lookup(self, issuer: str, subject: str) -> str | None:
        self.lookups.append((issuer, subject))
        return self.account_id


class Contexts:
    def __init__(self, context: AuthorizationContext) -> None:
        self.context = context
        self.accounts: list[str] = []

    def resolve(self, account_id: str) -> AuthorizationContext:
        self.accounts.append(account_id)
        return self.context


@pytest.fixture
def context() -> AuthorizationContext:
    return AuthorizationContext(
        active=True,
        session_version=4,
        permissions=frozenset({"orders.read", "orders.write", "users.read"}),
        roles=frozenset({"operator"}),
        attributes={"tenant": "tenant-1", "region": "west"},
    )


def _principal() -> Principal:
    return Principal(
        subject="token-subject", issuer="issuer", scopes=frozenset({"read"})
    )


def test_bearer_link_projects_account_context(context: AuthorizationContext) -> None:
    from rn_forge.auth.linking import link_bearer_principal

    accounts = Accounts("account-1")
    contexts = Contexts(context)
    linked = link_bearer_principal(
        _principal(),
        accounts=accounts,
        contexts=contexts,
        scope_map={"read": frozenset(context.permissions)},
    )
    assert linked.subject == "account-1"
    assert linked.external_subject == "token-subject"
    assert linked.roles == context.roles
    assert linked.attributes == context.attributes
    assert accounts.lookups == [("issuer", "token-subject")]
    assert contexts.accounts == ["account-1"]


def test_bearer_link_limits_permissions_by_scope_map(
    context: AuthorizationContext,
) -> None:
    from rn_forge.auth.linking import link_bearer_principal

    linked = link_bearer_principal(
        _principal(),
        accounts=Accounts("a"),
        contexts=Contexts(context),
        scope_map={"read": frozenset({"orders.read"})},
    )
    assert linked.permissions == frozenset({"orders.read"})


def test_unmapped_scope_allows_nothing(context: AuthorizationContext) -> None:
    from rn_forge.auth.linking import link_bearer_principal

    linked = link_bearer_principal(
        _principal(), accounts=Accounts("a"), contexts=Contexts(context), scope_map={}
    )
    assert linked.permissions == frozenset()


@pytest.mark.parametrize("account_id", [None])
def test_unlinked_subject_raises(account_id: str | None) -> None:
    from rn_forge.auth.linking import PrincipalLinkError, link_bearer_principal

    principal = _principal()
    accounts = Accounts(account_id)
    contexts = Contexts(AuthorizationContext(active=True, session_version=1))
    with pytest.raises(
        PrincipalLinkError, match="^No account is linked to the token subject$"
    ):
        link_bearer_principal(
            principal, accounts=accounts, contexts=contexts, scope_map={}
        )


def test_missing_issuer_raises_without_lookup() -> None:
    from rn_forge.auth.linking import PrincipalLinkError, link_bearer_principal

    accounts = Accounts("unused")
    principal = Principal(subject="sub")
    contexts = Contexts(AuthorizationContext(active=True, session_version=1))
    with pytest.raises(
        PrincipalLinkError, match="^No account is linked to the token subject$"
    ):
        link_bearer_principal(
            principal, accounts=accounts, contexts=contexts, scope_map={}
        )
    assert accounts.lookups == []


def test_inactive_account_raises() -> None:
    from rn_forge.auth.linking import PrincipalLinkError, link_bearer_principal

    principal = _principal()
    accounts = Accounts("a")
    contexts = Contexts(AuthorizationContext(active=False, session_version=1))
    with pytest.raises(PrincipalLinkError, match="^The account is not active$"):
        link_bearer_principal(
            principal, accounts=accounts, contexts=contexts, scope_map={}
        )


@pytest.mark.parametrize(
    ("attributes", "expected"),
    [({"tenant": "t"}, "t"), ({"tenant": 3}, None), ({}, None)],
)
def test_tenant_is_a_string_or_none(
    attributes: dict[str, object], expected: str | None
) -> None:
    from rn_forge.auth.linking import link_bearer_principal

    linked = link_bearer_principal(
        _principal(),
        accounts=Accounts("a"),
        contexts=Contexts(
            AuthorizationContext(active=True, session_version=1, attributes=attributes)
        ),
        scope_map={},
    )
    assert linked.tenant == expected


@pytest.mark.parametrize(
    ("attributes", "tenant"),
    [({"tenant": "t"}, "t"), ({"tenant": 4}, None), ({}, None)],
)
def test_session_principal_projection(
    attributes: dict[str, object], tenant: str | None
) -> None:
    from rn_forge.auth.linking import session_principal

    auth_time = datetime(2026, 1, 1, tzinfo=UTC)
    info = SessionInfo(
        account_id="a",
        session_version=1,
        provider="p",
        issuer="iss",
        external_subject="sub",
        created_at=auth_time,
        expires_at=auth_time,
        auth_time=auth_time,
        amr=frozenset({"pwd"}),
    )
    context = AuthorizationContext(
        active=True,
        session_version=1,
        permissions=frozenset({"a.read"}),
        roles=frozenset({"reader"}),
        attributes=attributes,
    )
    principal = session_principal(info, context)
    assert principal.subject == "a"
    assert principal.mechanism == "session"
    assert principal.auth_time == auth_time
    assert principal.amr == frozenset({"pwd"})
    assert principal.permissions == context.permissions
    assert principal.tenant == tenant
    assert principal.issuer == "iss"
    assert principal.external_subject == "sub"
    assert principal.roles == context.roles
    assert principal.attributes == context.attributes
