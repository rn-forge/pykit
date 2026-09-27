"""Public API for ``rn_forge.commons``.

Import from this package when you want the common helpers without reaching
into individual modules::

    from rn_forge.commons import AppLogger, Config, DictUtils, JsonUtils

    logger = AppLogger.initialize(root_logger_name="my-service")
    cfg = Config("config")
    logger.info("database.host={}", cfg.get("database.host"))

The re-export surface covers configuration, collections, dataclasses,
logging, subprocesses, task execution, and general utility helpers.
"""

# Modules are grouped by kind of mechanism (lang, fs, data, logging, runtime,
# integration); public class names are unaffected and stay re-exported here.
# The developer-tooling surface lives in two packages that depend on this one:
# `rn-forge-cli` (Typer wiring, standard options, exit codes) and
# `rn-forge-tooling` (state, templates, generation, install, docs checks).
# There are deliberately no compatibility re-exports in either direction —
# that would reverse the dependency, and `.importlinter` proves it does not
# happen. See `docs/guides/installation.md`.

from rn_forge.commons.config import Config
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.findings import Finding, Severity
from rn_forge.commons.fs.blocks import ManagedBlock
from rn_forge.commons.fs.documents import (
    ConfigFormat,
    DocumentError,
    DocumentUtils,
    JsonUtils,
    YamlUtils,
)
from rn_forge.commons.fs.hashing import ContentHash
from rn_forge.commons.fs.locks import DirectoryLock, atomic_symlink
from rn_forge.commons.fs.paths import PathUtils
from rn_forge.commons.integration.messaging import (
    AsyncMessageBus,
    HandlerRegistry,
    InMemoryMessageBus,
    MessageBus,
)
from rn_forge.commons.integration.objects import (
    AsyncObjectStore,
    InMemoryObjectStore,
    ObjectNotFound,
    ObjectStore,
)
from rn_forge.commons.integration.secrets import (
    AsyncSecretStore,
    EnvSecretStore,
    SecretNotFound,
    SecretStore,
)
from rn_forge.commons.lang.collections import (
    DictUtils,
    ListUtils,
    MergeResult,
)
from rn_forge.commons.lang.dataclasses import (
    DataclassMixin,
    LenientDataclassMixin,
    StrictDataclassMixin,
)
from rn_forge.commons.lang.reflection import ReflectUtils
from rn_forge.commons.lang.types import JsonValue
from rn_forge.commons.lang.utils import AppUtils, Base64
from rn_forge.commons.logging import (
    AppLogger,
    LoggingConfig,
)
from rn_forge.commons.runtime.console import AppConsole, OutputMode, console
from rn_forge.commons.runtime.environment import Environment
from rn_forge.commons.runtime.plugins import EntryPointLoader, PluginError
from rn_forge.commons.runtime.subprocess import Process
from rn_forge.commons.runtime.tasks import Task, TaskPool

__all__ = [
    "AppConsole",
    "AppException",
    "AppLogger",
    "AppUtils",
    "AsyncMessageBus",
    "AsyncObjectStore",
    "AsyncSecretStore",
    "Base64",
    "Config",
    "ConfigFormat",
    "ContentHash",
    "DataclassMixin",
    "DirectoryLock",
    "DictUtils",
    "DocumentError",
    "DocumentUtils",
    "EntryPointLoader",
    "EnvSecretStore",
    "Environment",
    "Finding",
    "HandlerRegistry",
    "InMemoryMessageBus",
    "InMemoryObjectStore",
    "JsonUtils",
    "LenientDataclassMixin",
    "JsonValue",
    "ListUtils",
    "LoggingConfig",
    "ManagedBlock",
    "MergeResult",
    "MessageBus",
    "ObjectNotFound",
    "ObjectStore",
    "OutputMode",
    "PathUtils",
    "PluginError",
    "Process",
    "ReflectUtils",
    "SecretNotFound",
    "SecretStore",
    "Severity",
    "StrictDataclassMixin",
    "Task",
    "TaskPool",
    "YamlUtils",
    "atomic_symlink",
    "console",
]
