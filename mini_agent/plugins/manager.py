import asyncio
import inspect
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple

from pydantic import BaseModel, Field

from mini_agent.plugins.catalog import PluginCatalog, PluginSpec
from mini_agent.plugins.context import (
    EventHandler,
    PluginContext,
    PluginKVStore,
    PluginRegistrationTracker,
)
from mini_agent.plugins.state import PluginState, PluginStateStore
from mini_agent.tools.registry import ToolRegistry


PluginSetup = Callable[[PluginContext], None]
PluginTeardown = Callable[[PluginContext], Any]


class PluginLoadResult(BaseModel):
    loaded: List[str] = Field(default_factory=list)
    failed: Dict[str, str] = Field(default_factory=dict)


class PluginSummary(BaseModel):
    id: str
    source: str
    name: str
    enabled: bool
    loaded: bool
    locked: bool = False
    tool_count: int = 0
    event_count: int = 0
    last_error: str = ""
    updated_at: str = ""
    requires_restart: bool = False


class PluginActionResult(BaseModel):
    ok: bool
    plugin: PluginSummary
    requires_restart: bool = False
    message: str = ""


@dataclass
class PluginRuntime:
    source: str
    name: str
    id: str
    plugin_dir: Path
    setup: PluginSetup
    teardown: Optional[PluginTeardown]
    context: PluginContext
    tracker: PluginRegistrationTracker
    module: Optional[ModuleType] = None


class PluginManager:
    def __init__(
        self,
        workspace: Path,
        tools: ToolRegistry,
        builtin_plugins: Optional[Mapping[str, PluginSetup]] = None,
        locked_plugins: Optional[Set[Tuple[str, str]]] = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.plugins_dir = self.workspace / "plugins"
        self.tools = tools
        self.kv_store = PluginKVStore(self.workspace / "agent.db")
        self.state_store = PluginStateStore(self.workspace / "agent.db")
        self._event_handlers: Dict[str, List[EventHandler]] = {}
        self._plugin_ids_by_name: Dict[str, List[str]] = {}
        self._trackers: Dict[str, PluginRegistrationTracker] = {}
        self._active: Dict[str, PluginRuntime] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._lock_loop: Optional[asyncio.AbstractEventLoop] = None
        self.builtin_plugins = dict(builtin_plugins or {})
        self.locked_plugins = set(locked_plugins or set())

    def discover(self) -> List[Path]:
        if not self.plugins_dir.exists():
            return []
        return sorted(
            path / "plugin.py"
            for path in self.plugins_dir.iterdir()
            if (path / "plugin.py").exists()
        )

    def list_plugins(self) -> List[PluginSummary]:
        return [
            self._summary_for_spec(spec, self._ensure_state(spec))
            for spec in self._discover_specs()
        ]

    def load_all(self) -> PluginLoadResult:
        result = PluginLoadResult()
        for spec in self._discover_specs():
            state = self._ensure_state(spec)
            if not state.enabled:
                continue
            if spec.id in self._active:
                result.loaded.append(spec.name)
                continue

            error = self._load_spec(spec)
            if error is None:
                self.state_store.set_loaded(spec.source, spec.name)
                result.loaded.append(spec.name)
            else:
                self.state_store.set_error(spec.source, spec.name, error)
                result.failed[spec.name] = error
        return result

    async def enable(self, source: str, name: str) -> PluginActionResult:
        async with self._get_lock():
            spec = self._find_spec(source, name)
            if spec is None:
                return self._missing_result(source, name)

            self.state_store.set_enabled(source, name, True)
            if spec.id in self._active:
                return PluginActionResult(
                    ok=True,
                    plugin=self._summary_for_spec(spec, self.state_store.get(source, name)),
                    message="插件已经启用",
                )

            error = self._load_spec(spec)
            if error is not None:
                state = self.state_store.set_error(source, name, error)
                return PluginActionResult(
                    ok=False,
                    plugin=self._summary_for_spec(spec, state),
                    message=f"插件加载失败：{error}",
                )

            state = self.state_store.set_loaded(source, name)
            return PluginActionResult(
                ok=True,
                plugin=self._summary_for_spec(spec, state),
                message="已启用并立即生效",
            )

    async def disable(self, source: str, name: str) -> PluginActionResult:
        async with self._get_lock():
            spec = self._find_spec(source, name)
            if spec is None:
                return self._missing_result(source, name)

            state = self._ensure_state(spec)
            if self._is_locked(spec) or state.locked:
                return PluginActionResult(
                    ok=False,
                    plugin=self._summary_for_spec(spec, state),
                    message="系统插件不可关闭",
                )

            state = self.state_store.set_enabled(source, name, False)
            teardown_error = await self._unload(source, name, call_teardown=True)
            if teardown_error:
                state = self.state_store.set_error(source, name, teardown_error)
                message = f"已禁用，但清理时出错：{teardown_error}"
            else:
                message = "已禁用并立即生效"

            return PluginActionResult(
                ok=True,
                plugin=self._summary_for_spec(spec, state),
                message=message,
            )

    async def reload(self, source: str, name: str) -> PluginActionResult:
        async with self._get_lock():
            spec = self._find_spec(source, name)
            if spec is None:
                return self._missing_result(source, name)

            self.state_store.set_enabled(source, name, True)
            teardown_error = await self._unload(source, name, call_teardown=True)
            error = self._load_spec(spec)
            if error is not None:
                combined_error = error
                if teardown_error:
                    combined_error = f"{error}; teardown: {teardown_error}"
                state = self.state_store.set_error(source, name, combined_error)
                return PluginActionResult(
                    ok=False,
                    plugin=self._summary_for_spec(spec, state),
                    message=f"插件重载失败：{combined_error}",
                )

            state = self.state_store.set_loaded(source, name)
            if teardown_error:
                state = self.state_store.set_error(source, name, teardown_error)
            return PluginActionResult(
                ok=True,
                plugin=self._summary_for_spec(spec, state),
                message="已重载并立即生效",
            )

    async def emit(self, event_name: str, event: Dict[str, Any]) -> None:
        for handler in list(self._event_handlers.get(event_name, [])):
            try:
                value = handler(event)
                if inspect.isawaitable(value):
                    await value
            except Exception:
                continue

    def kv_get(self, plugin_name: str, key: str, default: Any = None) -> Any:
        return self.kv_store.get(
            self._resolve_plugin_id(plugin_name),
            key,
            default,
        )

    def _discover_specs(self) -> List[PluginSpec]:
        builtin_specs = {
            name: PluginSpec(
                source="builtin",
                name=name,
                setup=setup,
                default_enabled=True,
                locked=("builtin", name) in self.locked_plugins,
            )
            for name, setup in self.builtin_plugins.items()
        }
        specs = list(PluginCatalog(self.workspace, builtin_specs).discover())
        return sorted(specs, key=_spec_sort_key)

    def _get_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    def _find_spec(self, source: str, name: str) -> Optional[PluginSpec]:
        for spec in self._discover_specs():
            if spec.source == source and spec.name == name:
                return spec
        return None

    def _ensure_state(self, spec: PluginSpec) -> PluginState:
        return self.state_store.ensure(
            spec.source,
            spec.name,
            default_enabled=spec.default_enabled,
            locked=self._is_locked(spec),
        )

    def _load_spec(self, spec: PluginSpec) -> Optional[str]:
        plugin_id = spec.id
        tracker = PluginRegistrationTracker()
        module: Optional[ModuleType] = None
        plugin_dir = spec.plugin_dir or self.plugins_dir / spec.name

        try:
            setup = spec.setup
            teardown = None
            if setup is None:
                plugin_file = plugin_dir / "plugin.py"
                module = _load_module(spec.name, plugin_file)
                setup = getattr(module, "setup")
                teardown = getattr(module, "teardown", None)

            context = PluginContext(
                name=spec.name,
                plugin_id=plugin_id,
                workspace=self.workspace,
                plugin_dir=plugin_dir,
                tools=self.tools,
                kv_store=self.kv_store,
                event_handlers=self._event_handlers,
                tracker=tracker,
            )
            setup(context)
        except Exception as exc:  # noqa: BLE001 - one bad plugin must not stop runtime.
            self._remove_tracked_resources(plugin_id, tracker)
            return str(exc)

        runtime = PluginRuntime(
            source=spec.source,
            name=spec.name,
            id=plugin_id,
            plugin_dir=plugin_dir,
            setup=setup,
            teardown=teardown,
            context=context,
            tracker=tracker,
            module=module,
        )
        self._active[plugin_id] = runtime
        self._trackers[plugin_id] = tracker
        self._remember_plugin_id(spec.name, plugin_id)
        return None

    async def _unload(
        self,
        source: str,
        name: str,
        *,
        call_teardown: bool,
    ) -> Optional[str]:
        plugin_id = f"{source}:{name}"
        runtime = self._active.pop(plugin_id, None)
        tracker = self._trackers.pop(plugin_id, None)
        teardown_error = None

        if runtime is not None:
            tracker = runtime.tracker
            if call_teardown and runtime.teardown is not None:
                try:
                    value = runtime.teardown(runtime.context)
                    if inspect.isawaitable(value):
                        await value
                except Exception as exc:  # noqa: BLE001 - cleanup must continue.
                    teardown_error = str(exc)

        if tracker is not None:
            self._remove_tracked_resources(plugin_id, tracker)
        self._forget_plugin_id(name, plugin_id)
        return teardown_error

    def _remove_tracked_resources(
        self,
        plugin_id: str,
        tracker: PluginRegistrationTracker,
    ) -> None:
        self.tools.unregister_source("plugin", plugin_id)
        for event_name, handler in list(tracker.subscribed_events):
            handlers = self._event_handlers.get(event_name)
            if handlers is None:
                continue
            self._event_handlers[event_name] = [
                existing for existing in handlers if existing is not handler
            ]
            if not self._event_handlers[event_name]:
                self._event_handlers.pop(event_name, None)

    def _summary_for_spec(
        self,
        spec: PluginSpec,
        state: Optional[PluginState],
    ) -> PluginSummary:
        if state is None:
            state = self._ensure_state(spec)
        tracker = self._trackers.get(spec.id)
        return PluginSummary(
            id=spec.id,
            source=spec.source,
            name=spec.name,
            enabled=state.enabled,
            loaded=spec.id in self._active,
            locked=state.locked or self._is_locked(spec),
            tool_count=len(tracker.registered_tools) if tracker else 0,
            event_count=len(tracker.subscribed_events) if tracker else 0,
            last_error=state.last_error,
            updated_at=state.updated_at,
        )

    def _missing_result(self, source: str, name: str) -> PluginActionResult:
        plugin_id = f"{source}:{name}"
        return PluginActionResult(
            ok=False,
            plugin=PluginSummary(
                id=plugin_id,
                source=source,
                name=name,
                enabled=False,
                loaded=False,
                last_error="插件不存在",
            ),
            message="插件不存在",
        )

    def _is_locked(self, spec: PluginSpec) -> bool:
        return spec.locked or (spec.source, spec.name) in self.locked_plugins

    def _remember_plugin_id(self, name: str, plugin_id: str) -> None:
        plugin_ids = self._plugin_ids_by_name.setdefault(name, [])
        if plugin_id not in plugin_ids:
            plugin_ids.append(plugin_id)

    def _forget_plugin_id(self, name: str, plugin_id: str) -> None:
        plugin_ids = self._plugin_ids_by_name.get(name)
        if plugin_ids is None:
            return
        self._plugin_ids_by_name[name] = [
            existing for existing in plugin_ids if existing != plugin_id
        ]
        if not self._plugin_ids_by_name[name]:
            self._plugin_ids_by_name.pop(name, None)

    def _resolve_plugin_id(self, plugin_name: str) -> str:
        if ":" in plugin_name:
            return plugin_name
        plugin_ids = self._plugin_ids_by_name.get(plugin_name, [])
        if len(plugin_ids) == 1:
            return plugin_ids[0]
        return plugin_name


def _spec_sort_key(spec: PluginSpec) -> Tuple[int, str]:
    source_order = 0 if spec.source == "builtin" else 1
    return source_order, spec.name


def _load_module(name: str, plugin_file: Path) -> ModuleType:
    if not plugin_file.exists():
        raise ImportError(f"cannot load plugin: {plugin_file}")
    module = ModuleType(f"mini_agent_plugin_{name}")
    module.__file__ = str(plugin_file)
    source = plugin_file.read_text(encoding="utf-8")
    exec(compile(source, str(plugin_file), "exec"), module.__dict__)
    return module
