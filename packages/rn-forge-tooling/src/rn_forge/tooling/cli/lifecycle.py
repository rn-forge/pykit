"""The lifecycle verbs as Typer commands, for a declared ``[cli.lifecycle]`` table.

A repository does not import this. Its ``[cli.lifecycle]`` table names it::

    [cli.lifecycle]
    product = "golden_tool.product:PRODUCT"
    target = "rn_forge.tooling.cli.lifecycle:lifecycle_commands"

and :meth:`rn_forge.cli.CliApp.from_config` imports both by name, calls
:func:`lifecycle_commands` with the product and the declared verbs, and mounts
the result at the root of the application — ``golden-tool doctor``, not
``golden-tool lifecycle doctor``. The indirection is the import contract:
``rn-forge-cli`` may not import this package, so it cannot know this module
except as a string in a repository's configuration.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer

from rn_forge.cli import CliOptions, YesOption
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.commons.runtime.console import OutputMode, console

from rn_forge.tooling.install import lifecycle
from rn_forge.tooling.install.product import ToolProduct
from rn_forge.tooling.install.release import LocalArchive

__all__ = ["VERBS", "lifecycle_commands"]

VERBS = ("install", "upgrade", "uninstall", "cleanup", "status", "doctor")
"""Every verb this module can mount, in ``--help`` order."""


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
