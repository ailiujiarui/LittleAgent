import importlib.util
import inspect
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field

from mini_agent.plugins.context import EventHandler, PluginContext, PluginKVStore
from mini_agent.tools.registry import ToolRegistry


class PluginLoadResult(BaseModel):
    loaded: List[str] = Field(default_factory=list)
    failed: Dict[str, str] = Field(default_factory=dict)


class PluginManager:
    def __init__(
        self,
        workspace: Path,
        tools: ToolRegistry,
        builtin_plugins: Optional[Mapping[str, Callable[[PluginContext], None]]] = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.plugins_dir = self.workspace / "plugins"
        self.tools = tools
        self.kv_store = PluginKVStore(self.workspace / "agent.db")
        self._event_handlers: Dict[str, List[EventHandler]] = {}
        self.builtin_plugins = dict(builtin_plugins or {})

    def discover(self) -> List[Path]:
        if not self.plugins_dir.exists():
            return []
        return sorted(
            path / "plugin.py"
            for path in self.plugins_dir.iterdir()
            if (path / "plugin.py").exists()
        )

    def load_all(self) -> PluginLoadResult:
        result = PluginLoadResult()
        for name, setup in sorted(self.builtin_plugins.items()):
            self._load_plugin(name, setup, result)

        for plugin_file in self.discover():
            name = plugin_file.parent.name
            try:
                module = _load_module(name, plugin_file)
                setup = getattr(module, "setup")
            except Exception as exc:  # noqa: BLE001 - one bad plugin must not stop startup.
                result.failed[name] = str(exc)
                continue
            self._load_plugin(name, setup, result, plugin_dir=plugin_file.parent)
        return result

    def _load_plugin(
        self,
        name: str,
        setup: Callable[[PluginContext], None],
        result: PluginLoadResult,
        plugin_dir: Optional[Path] = None,
    ) -> None:
        try:
            ctx = PluginContext(
                name=name,
                workspace=self.workspace,
                plugin_dir=plugin_dir or self.plugins_dir / name,
                tools=self.tools,
                kv_store=self.kv_store,
                event_handlers=self._event_handlers,
            )
            setup(ctx)
        except Exception as exc:  # noqa: BLE001 - one bad plugin must not stop startup.
            result.failed[name] = str(exc)
            return
        result.loaded.append(name)

    async def emit(self, event_name: str, event: Dict[str, Any]) -> None:
        for handler in list(self._event_handlers.get(event_name, [])):
            try:
                value = handler(event)
                if inspect.isawaitable(value):
                    await value
            except Exception:
                continue

    def kv_get(self, plugin_name: str, key: str, default: Any = None) -> Any:
        return self.kv_store.get(plugin_name, key, default)


def _load_module(name: str, plugin_file: Path) -> ModuleType:
    module_name = f"mini_agent_plugin_{name}"
    spec = importlib.util.spec_from_file_location(module_name, plugin_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin: {plugin_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
