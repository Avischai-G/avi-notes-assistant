"""Strict local-stdio client for the scoped Notion MCP server.

The bearer token is passed only in the child process environment. It is never
placed in an argv entry, serialized into an agent prompt, or written to logs.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import shutil
import sys
import threading
from collections.abc import Mapping
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Self

MCP_PACKAGE = "notion-mcp-server"
MCP_VERSION = "2.13.0"
MCP_PACKAGE_SPEC = f"{MCP_PACKAGE}@{MCP_VERSION}"

STEADY_STATE_OPERATIONS = (
    "create_page",
    "set_page_title",
    "set_page_property",
    "query_database",
    "archive_page",
    "restore_page",
    "get_page_markdown",
    "update_page_markdown",
    "add_page_comment",
    "list_comments",
)
MCP_TOOL_NAMES = frozenset({"notion_describe", "notion_execute"})

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
_OPERATION_ROW = re.compile(r"^\| `([^`]+)` \|", re.MULTILINE)
_TOKEN_PREFIXES = ("ntn" + "_", "secret" + "_")
_TOKENISH = re.compile(
    rf"\b(?:{'|'.join(re.escape(prefix) for prefix in _TOKEN_PREFIXES)})"
    r"[A-Za-z0-9._-]+"
)


class NotionConfigurationError(RuntimeError):
    """The Notion runtime is absent or wider than the approved boundary."""


class NotionMcpError(RuntimeError):
    """A scoped MCP operation failed without exposing sensitive response data."""


@dataclass(frozen=True)
class McpDiscovery:
    tools: frozenset[str]
    operations: frozenset[str]


@dataclass(frozen=True)
class StdioChildSpec:
    command: str
    args: tuple[str, ...]
    env: dict[str, str] = field(repr=False)
    cwd: Path


class NotionMcpClient(Protocol):
    """Small deterministic surface used by the task-store adapter."""

    @property
    def discovery(self) -> McpDiscovery: ...

    def execute(self, operation: str, payload: Mapping[str, Any]) -> Any: ...

    def close(self) -> None: ...


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise NotionConfigurationError(f"Missing required Notion setting: {name}")
    return value


def _notion_id(env: Mapping[str, str], name: str) -> str:
    value = _required(env, name)
    if not _ID_PATTERN.fullmatch(value.replace("-", "")):
        raise NotionConfigurationError(f"{name} must be a 32-hex-character Notion id")
    return value


def _token(env: Mapping[str, str]) -> str:
    value = _required(env, "NOTION_TOKEN")
    if not value.startswith(_TOKEN_PREFIXES):
        raise NotionConfigurationError(
            "NOTION_TOKEN does not look like a Notion internal-connection token"
        )
    return value


@dataclass(frozen=True)
class NotionConfig:
    """Existing-database-only configuration with a compiled least-privilege surface."""

    token: str = field(repr=False)
    tasks_database_id: str = field(repr=False)
    allowed_operations: str = ",".join(STEADY_STATE_OPERATIONS)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> NotionConfig:
        values = os.environ if env is None else env
        return cls(
            token=_token(values),
            tasks_database_id=_notion_id(values, "NOTION_TASKS_DATABASE_ID"),
        )

    def child_environment(self) -> dict[str, str]:
        return _minimal_child_environment(self.token, self.allowed_operations)


def _minimal_child_environment(token: str, operations: str) -> dict[str, str]:
    """Pass only what the local child needs, not the parent's secret-rich env."""
    path = os.environ.get("PATH", "")
    if not path:
        raise NotionConfigurationError("PATH is required to launch the MCP child")
    return {
        "PATH": path,
        "NOTION_TOKEN": token,
        "NOTION_ALLOWED_OPERATIONS": operations,
        "MCP_TRANSPORT": "stdio",
        "NO_COLOR": "1",
        "NPM_CONFIG_OFFLINE": "true",
        "NPM_CONFIG_UPDATE_NOTIFIER": "false",
        "NPM_CONFIG_USERCONFIG": os.devnull,
    }


def _stdio_child_spec(
    config: NotionConfig,
    project_root: Path,
    npx: str,
) -> StdioChildSpec:
    return StdioChildSpec(
        command=npx,
        args=("--yes", "--offline", MCP_PACKAGE_SPEC),
        env=config.child_environment(),
        cwd=project_root,
    )


def _redact(value: str, *secrets: str | None) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "<redacted-notion-secret>")
    return _TOKENISH.sub("<redacted-notion-token>", value)


class _RedactingPipe(io.TextIOBase):
    """Give subprocess a real fd while redacting every complete stderr line."""

    def __init__(self, target: io.TextIOBase, *secrets: str):
        self._target = target
        self._secrets = secrets
        read_fd, write_fd = os.pipe()
        self._reader = os.fdopen(read_fd, "r", encoding="utf-8", errors="replace")
        self._writer = os.fdopen(write_fd, "w", encoding="utf-8")
        self._thread = threading.Thread(
            target=self._pump, name="notion-mcp-stderr", daemon=True
        )
        self._thread.start()

    def _pump(self) -> None:
        for line in self._reader:
            self._target.write(_redact(line, *self._secrets))
            self._target.flush()

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        return self._writer.write(text)

    def flush(self) -> None:
        if not self._writer.closed:
            self._writer.flush()

    def fileno(self) -> int:
        return self._writer.fileno()

    def isatty(self) -> bool:
        return False

    def close(self) -> None:
        if self.closed:
            return
        try:
            self._writer.close()
            self._thread.join(timeout=2)
        finally:
            self._reader.close()
            super().close()


class _LoopThread:
    """Keep every MCP session on one persistent asyncio event loop."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="notion-mcp-loop", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise NotionMcpError("Timed out starting the Notion MCP event loop")

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self._ready.set()
        self.loop.run_forever()
        self.loop.close()

    def submit(self, coroutine: Any, timeout: float = 45.0) -> Any:
        if not self._thread.is_alive():
            if hasattr(coroutine, "close"):
                coroutine.close()
            raise NotionMcpError("Notion MCP event loop is not running")
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise NotionMcpError(
                "Notion MCP call timed out; a write outcome may be unknown, so "
                "re-read the scoped board before deciding whether to repeat it"
            ) from exc

    def close(self) -> None:
        if self._thread.is_alive():
            self.loop.call_soon_threadsafe(self.loop.stop)
            self._thread.join(timeout=5)


class AdkNotionMcpClient:
    """Run the pinned awkoy server through Google ADK's stdio MCP toolset."""

    def __init__(
        self,
        config: NotionConfig,
        *,
        project_root: Path | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._config = config
        self._project_root = (project_root or _PROJECT_ROOT).resolve()
        self._timeout_seconds = timeout_seconds
        self._loop_thread = _LoopThread()
        self._toolset: Any = None
        self._errlog: _RedactingPipe | None = None
        self._closed = False
        try:
            self._discovery = self._loop_thread.submit(
                self._initialize(), timeout=timeout_seconds + 10
            )
        except Exception:
            try:
                if self._toolset is not None:
                    self._loop_thread.submit(
                        self._toolset.close(), timeout=self._timeout_seconds
                    )
            finally:
                if self._errlog is not None:
                    self._errlog.close()
                self._loop_thread.close()
            raise

    async def _initialize(self) -> McpDiscovery:
        try:
            from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
            from mcp import StdioServerParameters
        except ImportError as exc:
            raise NotionConfigurationError(
                "Google ADK's MCP support is missing; install requirements.txt "
                "with the google-adk[mcp] extra"
            ) from exc

        npx = shutil.which("npx")
        if not npx:
            raise NotionConfigurationError(
                "npx was not found; Node.js 20 or newer is required"
            )
        package_lock = self._project_root / "package-lock.json"
        local_package = (
            self._project_root / "node_modules" / MCP_PACKAGE / "package.json"
        )
        if not package_lock.is_file() or not local_package.is_file():
            raise NotionConfigurationError(
                "Pinned Notion MCP dependency is not installed; run npm ci in "
                "the application root"
            )
        try:
            installed = json.loads(local_package.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise NotionConfigurationError(
                "Could not validate the installed Notion MCP package"
            ) from exc
        if (
            installed.get("name") != MCP_PACKAGE
            or installed.get("version") != MCP_VERSION
        ):
            raise NotionConfigurationError(
                f"Expected {MCP_PACKAGE_SPEC}; run npm ci to restore the lockfile"
            )

        child = _stdio_child_spec(self._config, self._project_root, npx)
        params = StdioServerParameters(
            command=child.command,
            args=list(child.args),
            env=child.env,
            cwd=child.cwd,
        )
        self._errlog = _RedactingPipe(
            sys.stderr,
            self._config.token,
            self._config.tasks_database_id,
        )
        self._toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=params, timeout=self._timeout_seconds
            ),
            errlog=self._errlog,
            use_mcp_resources=False,
        )

        tools = await self._toolset.get_tools()
        tool_names = frozenset(tool.name for tool in tools)
        if tool_names != MCP_TOOL_NAMES:
            await self._toolset.close()
            raise NotionConfigurationError(
                "Unexpected MCP tool discovery surface: " + ",".join(sorted(tool_names))
            )

        try:
            contents = await self._toolset.read_resource("operations-index")
        except Exception as exc:
            await self._toolset.close()
            raise NotionConfigurationError(
                "Could not read the MCP operation index"
            ) from exc
        text_parts = [
            getattr(content, "text", "")
            for content in contents
            if getattr(content, "text", "")
        ]
        operations = frozenset(_OPERATION_ROW.findall("\n".join(text_parts)))
        expected = frozenset(self._config.allowed_operations.split(","))
        if operations != expected:
            await self._toolset.close()
            missing = sorted(expected - operations)
            extra = sorted(operations - expected)
            raise NotionConfigurationError(
                "MCP operation discovery does not match the approved allowlist "
                f"(missing={missing}, extra={extra})"
            )
        return McpDiscovery(tools=tool_names, operations=operations)

    @property
    def discovery(self) -> McpDiscovery:
        return self._discovery

    async def _execute(self, operation: str, payload: Mapping[str, Any]) -> Any:
        if operation not in self._discovery.operations:
            raise NotionMcpError(f"Notion operation is not allowed: {operation}")
        if self._toolset is None:
            raise NotionMcpError("Notion MCP toolset is not initialized")

        try:
            # Use ADK's managed session, but intentionally avoid the toolset's
            # generic retry decorator: retrying a disconnected create call can
            # duplicate a write whose remote outcome is unknown.
            session = await self._toolset._mcp_session_manager.create_session()
            result = await asyncio.wait_for(
                session.call_tool(
                    "notion_execute",
                    arguments={"operation": operation, "payload": dict(payload)},
                ),
                timeout=self._timeout_seconds,
            )
            wire = result.model_dump(exclude_none=True, mode="json")
        except NotionMcpError:
            raise
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise NotionMcpError(
                f"Notion MCP timed out during {operation}; a write outcome may "
                "be unknown, so re-read the scoped board before repeating it"
            ) from exc
        except Exception as exc:
            clean = _redact(
                str(exc),
                self._config.token,
                self._config.tasks_database_id,
            )
            raise NotionMcpError(
                f"Notion MCP transport failed for {operation}: {clean}"
            ) from exc

        text_chunks = [
            part.get("text", "")
            for part in wire.get("content", [])
            if part.get("type") == "text"
        ]
        try:
            envelope = json.loads("".join(text_chunks))
        except (TypeError, json.JSONDecodeError) as exc:
            raise NotionMcpError(
                f"Notion MCP returned invalid JSON for {operation}"
            ) from exc
        if (
            wire.get("isError")
            or not isinstance(envelope, dict)
            or not envelope.get("ok")
        ):
            error = envelope.get("error", {}) if isinstance(envelope, dict) else {}
            code = str(error.get("code", "operation_failed"))
            message = _redact(
                str(error.get("message", "MCP operation failed")),
                self._config.token,
                self._config.tasks_database_id,
            )
            raise NotionMcpError(f"{operation} failed ({code}): {message}")
        return envelope.get("data")

    def execute(self, operation: str, payload: Mapping[str, Any]) -> Any:
        if self._closed:
            raise NotionMcpError("Notion MCP client is closed")
        return self._loop_thread.submit(
            self._execute(operation, payload), timeout=self._timeout_seconds + 10
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._toolset is not None:
                self._loop_thread.submit(
                    self._toolset.close(), timeout=self._timeout_seconds
                )
        finally:
            if self._errlog is not None:
                self._errlog.close()
            self._loop_thread.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
