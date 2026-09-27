"""Typer commands for a declared tool lifecycle."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Mapping, Self

import typer

from rn_forge.cli import CliApp, CliOptions, CliSurface, YesOption
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.documents import DocumentUtils
from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.commons.lang.utils import AppUtils
from rn_forge.commons.runtime.console import OutputMode, console

from rn_forge.tooling.install import lifecycle
from rn_forge.tooling.install.product import ToolProduct
from rn_forge.tooling.install.release import LocalArchive

__all__ = ["VERBS", "LifecycleSurface", "build_tool_app", "lifecycle_commands"]

VERBS = ("install", "upgrade", "uninstall", "cleanup", "status", "doctor")
"""Every verb this module can mount, in ``--help`` order."""

LIFECYCLE_KEY = "lifecycle"
"""The table :meth:`LifecycleSurface.load` reads by default."""


def lifecycle_commands(
    product: ToolProduct, verbs: Sequence[str] = VERBS
) -> typer.Typer:
    """Return a Typer app holding *verbs* as commands over *product*.

    Args:
        product: The product the commands act on.
        verbs: Which of :data:`VERBS` to include.

    Raises:
        AppException: *product* is not a :class:`ToolProduct`, or a verb is
            not one of :data:`VERBS`.
    """
    if not isinstance(product, ToolProduct):  # pyright: ignore[reportUnnecessaryIsInstance] - named by a config string
        raise AppException("{!r} is not a ToolProduct", product)
    unknown = sorted(set(verbs) - set(VERBS))
    if unknown:
        raise AppException("Unknown lifecycle verb(s): {}", ", ".join(unknown))

    app = typer.Typer()
    for verb in VERBS:
        if verb in verbs:
            _COMMANDS[verb](app, product)
    return app


@dataclass(frozen=True, slots=True)
class LifecycleSurface(DataclassMixin):
    """A declared ``[lifecycle]`` table: which verbs a tool exposes, and where.

    Args:
        product: Import path of the :class:`ToolProduct` the verbs act on.
        verbs: Which of :data:`VERBS` to expose. Default: all six.
        namespace: Sub-command group the verbs are mounted under, e.g.
            ``"self"`` for ``<tool> self status``. Default: mounted at the
            root of the application.
    """

    product: str
    verbs: tuple[str, ...] = VERBS
    namespace: str | None = None

    def __post_init__(self) -> None:
        unknown = [verb for verb in self.verbs if verb not in VERBS]
        if unknown:
            raise AppException(
                "Unknown lifecycle verb(s): {} (expected any of {})",
                ", ".join(unknown),
                ", ".join(VERBS),
            )
        duplicates = _duplicates(self.verbs)
        if duplicates:
            raise AppException("Duplicate lifecycle verb(s): {}", ", ".join(duplicates))
        if self.namespace is not None and (
            not self.namespace.strip() or any(char.isspace() for char in self.namespace)
        ):
            raise AppException("Invalid lifecycle namespace: {!r}", self.namespace)

    @classmethod
    def load(
        cls, source: str | Path | Mapping[str, Any], *, key: str = LIFECYCLE_KEY
    ) -> Self:
        """Read a lifecycle surface from a config document or an in-memory mapping.

        Args:
            source: A path to a TOML/YAML/JSON document, or an already-parsed
                mapping. Either may be the whole document (with the table
                under *key*) or the table itself.
            key: The table the surface lives under. Ignored when *source* is
                already the table.

        Raises:
            AppException: The document has no *key* table, or a declared
                value does not match its field's type.
        """
        data = (
            dict(source) if isinstance(source, Mapping) else DocumentUtils.read(source)
        )
        if key in data:
            data = data[key]
        elif "product" not in data:
            raise AppException("No [{}] table to build lifecycle verbs from", key)
        return cls.from_dict(dict(data))


def build_tool_app(
    source: str | Path | Mapping[str, Any],
    *,
    cli_key: str = "cli",
    lifecycle_key: str = LIFECYCLE_KEY,
    **typer_kwargs: Any,
) -> CliApp:
    """Build the application a repository's ``[cli]`` and ``[lifecycle]`` tables describe.

    This is the entry point for an installable tool. It builds the generic
    application `rn-forge-cli` describes from ``[cli]``, then — when the
    document also has a *lifecycle_key* table — mounts this module's verbs on
    top of it, at the root or under `LifecycleSurface.namespace`.

    Args:
        source: A path to the configuration document, or an already-parsed
            mapping. See :meth:`~rn_forge.cli.CliSurface.load`.
        cli_key: The table the generic surface lives under.
        lifecycle_key: The table the lifecycle verbs live under. A document
            without this table builds a plain application.
        **typer_kwargs: Forwarded to the :class:`~rn_forge.cli.CliApp`
            constructor.

    Raises:
        AppException: Either table is malformed, the namespace or a verb
            collides with a declared command name, or the product cannot be
            imported.
    """
    document = (
        dict(source) if isinstance(source, Mapping) else DocumentUtils.read(source)
    )
    surface = CliSurface.load(document, key=cli_key)
    app = CliApp.from_surface(surface, **typer_kwargs)
    if lifecycle_key not in document:
        return app

    declared = LifecycleSurface.load(document, key=lifecycle_key)
    occupied = (
        {declared.namespace} if declared.namespace is not None else set(declared.verbs)
    )
    collisions = occupied & {command.name for command in surface.commands}
    if collisions:
        raise AppException(
            "Duplicate command name(s): {}", ", ".join(sorted(collisions))
        )

    try:
        product = AppUtils.import_string(declared.product)
    except Exception as error:
        raise AppException(
            "Cannot import lifecycle product {!r}: {}", declared.product, error
        ) from error
    commands = lifecycle_commands(product, declared.verbs)
    if declared.namespace is not None:
        app.add_typer(
            commands,
            name=declared.namespace,
            help="Install, upgrade and check this tool itself.",
        )
    else:
        app.add_typer(commands)
    return app


def _duplicates(names: Iterable[str]) -> list[str]:
    """Names appearing more than once, in first-seen order."""
    seen: set[str] = set()
    repeated: list[str] = []
    for name in names:
        if name in seen and name not in repeated:
            repeated.append(name)
        seen.add(name)
    return repeated


def _emit(record: DataclassMixin, text: str) -> None:
    """Print *record* as JSON in ``--json`` mode, *text* otherwise."""
    if console.mode is OutputMode.JSON:
        console.emit(record.as_dict())
    else:
        console.success("{}", text)


def _add_install(app: typer.Typer, product: ToolProduct) -> None:
    @app.command("install")
    def install(
        version: Annotated[
            str | None,
            typer.Option("--version", help="Version to install. Default: latest."),
        ] = None,
        archive: Annotated[
            Path | None,
            typer.Option("--archive", help="Install from a local archive instead."),
        ] = None,
        force: Annotated[
            bool, typer.Option("--force", help="Reinstall the active version.")
        ] = False,
    ) -> None:
        """Install a release and make it the active version."""
        source = None
        if archive is not None:
            if version is None:
                raise typer.BadParameter("--archive needs --version")
            source = LocalArchive(archive, version)
        result = lifecycle.install(product, version=version, source=source, force=force)
        _emit(result, _install_text(result))


def _add_upgrade(app: typer.Typer, product: ToolProduct) -> None:
    @app.command("upgrade")
    def upgrade() -> None:
        """Install the latest release over the current install."""
        result = lifecycle.upgrade(product)
        _emit(result, _install_text(result))


def _add_uninstall(app: typer.Typer, product: ToolProduct) -> None:
    @app.command("uninstall")
    def uninstall(ctx: typer.Context, yes: YesOption = False) -> None:
        """Remove every installed version and everything the install put in place."""
        if not CliOptions.from_context(ctx, yes=yes).yes and not console.confirm(
            f"Remove {product.name} and every installed version?"
        ):
            raise typer.Abort()
        result = lifecycle.uninstall(product)
        _emit(
            result,
            f"{product.name} removed"
            if result.outcome == "removed"
            else f"{product.name} is not installed",
        )


def _add_cleanup(app: typer.Typer, product: ToolProduct) -> None:
    @app.command("cleanup")
    def cleanup(ctx: typer.Context, yes: YesOption = False) -> None:
        """Remove every installed version except the active one."""
        planned = lifecycle.cleanup(product, dry_run=True)
        if planned.removed and not (
            CliOptions.from_context(ctx, yes=yes).yes
            or console.confirm(
                f"Remove {', '.join(planned.removed)} (keeping {planned.kept})?"
            )
        ):
            raise typer.Abort()
        result = lifecycle.cleanup(product)
        _emit(
            result,
            f"removed {len(result.removed)} version(s), kept {result.kept}",
        )


def _add_status(app: typer.Typer, product: ToolProduct) -> None:
    @app.command("status")
    def status() -> None:
        """Show the running version and what is installed."""
        result = lifecycle.status(product)
        _emit(
            result,
            f"{result.product} {result.version} — installed: "
            f"{result.installed or 'none'} ({result.home})",
        )


def _add_doctor(app: typer.Typer, product: ToolProduct) -> None:
    @app.command("doctor")
    def doctor() -> None:
        """Check the install and the product's own health."""
        findings = lifecycle.doctor(product)
        if console.mode is OutputMode.JSON:
            console.emit({"findings": [finding.as_dict() for finding in findings]})
        else:
            for finding in findings:
                # `markup=False`: a finding's `[code]` is not Rich markup, and
                # the code is the part a reader searches for.
                console.print(f"{finding.severity}: {finding}", markup=False)
        if any(finding.is_error for finding in findings):
            raise typer.Exit(1)


def _install_text(result: lifecycle.InstallResult) -> str:
    if result.outcome == "already-current":
        return f"{result.product} {result.version} is already active"
    return (
        f"{result.product} {result.version} installed (was {result.previous or 'none'})"
    )


_COMMANDS = {
    "install": _add_install,
    "upgrade": _add_upgrade,
    "uninstall": _add_uninstall,
    "cleanup": _add_cleanup,
    "status": _add_status,
    "doctor": _add_doctor,
}
