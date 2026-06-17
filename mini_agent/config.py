import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - used on Python < 3.11
    import tomli as tomllib


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class LLMConfig(BaseModel):
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-v4-flash"


class OneBotConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    path: str = "/onebot/v11/ws"
    bot_uin: str = "0"
    allow_private: List[str] = Field(default_factory=list)
    groups: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    access_token: Optional[str] = None


class ProactiveSourceConfig(BaseModel):
    type: str
    name: str
    url: str


class ProactiveConfig(BaseModel):
    enabled: bool = False
    interval_seconds: int = 1800
    threshold: float = 0.65
    cooldown_minutes: int = 30
    daily_max_pushes: int = 8
    target_channel: str = "qq"
    target_chat_id: str = ""
    sources: List[ProactiveSourceConfig] = Field(default_factory=list)


class DashboardConfig(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8787
    access_token: str = ""


class MCPConfig(BaseModel):
    enabled: bool = True


class DriftConfig(BaseModel):
    enabled: bool = False
    min_interval_minutes: int = 120
    max_steps: int = 8


class XiaohongshuConfig(BaseModel):
    search_endpoint: str = "http://localhost:18060/mcp"
    search_api_key: str = ""


class AppConfig(BaseModel):
    workspace: Path = Path("workspace")
    llm: LLMConfig = Field(default_factory=LLMConfig)
    onebot: OneBotConfig = Field(default_factory=OneBotConfig)
    proactive: ProactiveConfig = Field(default_factory=ProactiveConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    drift: DriftConfig = Field(default_factory=DriftConfig)
    xiaohongshu: XiaohongshuConfig = Field(default_factory=XiaohongshuConfig)


def load_config(path: Optional[Path] = None) -> AppConfig:
    if path is None:
        path = Path("config.toml")
    path = Path(path)

    if path.exists():
        with path.open("rb") as file:
            raw = tomllib.load(file)
    else:
        raw = {}

    expanded = _expand_env(raw)
    return AppConfig.model_validate(expanded)


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda match: os.environ.get(match.group(1), ""), value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value
