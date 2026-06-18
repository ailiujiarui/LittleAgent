from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional

from mini_agent.plugins.context import PluginContext
from mini_agent.plugins.group_messages import setup as setup_group_messages


PluginSetup = Callable[[PluginContext], None]


@dataclass(frozen=True)
class PluginSpec:
    source: str
    name: str
    setup: Optional[PluginSetup] = None
    plugin_dir: Optional[Path] = None
    default_enabled: bool = False
    locked: bool = False

    @property
    def id(self) -> str:
        return f"{self.source}:{self.name}"


def builtin_plugin_specs(
    xiaohongshu_setup: Optional[PluginSetup] = None,
) -> Dict[str, PluginSpec]:
    return {
        "group_messages": PluginSpec(
            source="builtin",
            name="group_messages",
            setup=setup_group_messages,
            default_enabled=True,
        ),
        "xiaohongshu_search": PluginSpec(
            source="builtin",
            name="xiaohongshu_search",
            setup=xiaohongshu_setup,
            default_enabled=True,
        ),
    }


class PluginCatalog:
    def __init__(
        self,
        workspace: Path,
        builtin_plugins: Optional[Dict[str, PluginSpec]] = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.plugins_dir = self.workspace / "plugins"
        self.builtin_plugins = dict(builtin_plugins or {})

    def discover(self) -> Iterable[PluginSpec]:
        specs = list(self.builtin_plugins.values())
        if self.plugins_dir.exists():
            for plugin_dir in sorted(self.plugins_dir.iterdir()):
                plugin_file = plugin_dir / "plugin.py"
                if plugin_file.exists():
                    specs.append(
                        PluginSpec(
                            source="workspace",
                            name=plugin_dir.name,
                            plugin_dir=plugin_dir,
                            default_enabled=False,
                        )
                    )
        return specs
