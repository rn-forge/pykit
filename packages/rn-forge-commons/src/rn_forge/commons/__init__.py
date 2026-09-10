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

# Phase C moved the developer-tooling surface out of this package: cli,
# console, state, templates, DirectoryLock, atomic_symlink and
# extract_archive now live in `rn-forge-tooling`, which depends on this
# package. There are deliberately no compatibility re-exports — that would
# reverse the dependency. See `docs/guides/installation.md`.
# commons-owned: documents, ContentHash, atomic writes, backups, managed
# blocks, findings, path guards/root discovery, merge/flatten/diff helpers
# and EntryPointLoader.

from rn_forge.commons._typing import JsonValue
from rn_forge.commons.blocks import ManagedBlock
from rn_forge.commons.collections import (
    DictUtils,
    ListUtils,
    MergeResult,
)
from rn_forge.commons.config import Config
from rn_forge.commons.dataclasses import DataclassMixin
from rn_forge.commons.documents import (
    ConfigFormat,
    DocumentError,
    DocumentUtils,
    JsonUtils,
    YamlUtils,
)
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.findings import Finding, Severity
from rn_forge.commons.logging import (
    AppLogger,
    LoggingConfig,
)
from rn_forge.commons.messaging import (
    AsyncMessageBus,
    HandlerRegistry,
    InMemoryMessageBus,
    MessageBus,
)
from rn_forge.commons.objects import (
    AsyncObjectStore,
    InMemoryObjectStore,
    ObjectNotFound,
    ObjectStore,
)
from rn_forge.commons.plugins import EntryPointLoader, PluginError
from rn_forge.commons.reflection import ReflectUtils
from rn_forge.commons.secrets import (
    AsyncSecretStore,
    EnvSecretStore,
    SecretNotFound,
    SecretStore,
)
from rn_forge.commons.subprocess import Process
from rn_forge.commons.tasks import Task, TaskPool
from rn_forge.commons.utils import (
    AppUtils,
    Base64,
    ContentHash,
    Environment,
    PathUtils,
)

__all__ = [
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
    "JsonValue",
    "ListUtils",
    "LoggingConfig",
    "ManagedBlock",
    "MergeResult",
    "MessageBus",
    "ObjectNotFound",
    "ObjectStore",
    "PathUtils",
    "PluginError",
    "Process",
    "ReflectUtils",
    "SecretNotFound",
    "SecretStore",
    "Severity",
    "Task",
    "TaskPool",
    "YamlUtils",
]
