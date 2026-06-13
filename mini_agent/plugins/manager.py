import importlib.util
import inspect
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from mini_agent.plugins.context import EventHandler, PluginContext, PluginKVStore
from mini_agent.tools.registry import ToolRegistry


class PluginLoadResult(BaseModel):
    loaded: List[str] = Field(default_factory=list)
    failed: Dict[str, str] = Field(default_factory=dict)


class PluginManager:
    def __init__(self, workspace: Path, tools: ToolRegistry) -> None:
        self.workspace = Path(workspace)
        self.plugins_dir = self.workspace / "plugins"
        self.tools = tools
        self.kv_store = PluginKVStore(self.workspace / "agent.db")
        self._event_handlers: Dict[str, List[EventHandler]] = {}

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
        for plugin_file in self.discover():
            name = plugin_file.parent.name
            try:
                module = _load_module(name, plugin_file)
                setup = getattr(module, "setup")
                ctx = PluginContext(
                    name=name,
                    workspace=self.workspace,
                    plugin_dir=plugin_file.parent,
                    tools=self.tools,
                    kv_store=self.kv_store,
                    event_handlers=self._event_handlers,
                )
                setup(ctx)
            except Exception as exc:  # noqa: BLE001 - one bad plugin must not stop startup.
                result.failed[name] = str(exc)
                continue
            result.loaded.append(name)
        return result

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
