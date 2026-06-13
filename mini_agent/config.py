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
    base_url: str = "http://127.0.0.1:11434/v1"
    api_key: str = ""
    model: str = "qwen2.5:7b"


class OneBotConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    path: str = "/onebot/v11/ws"
    bot_uin: str = "0"
    allow_private: List[str] = Field(default_factory=list)
    groups: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    access_token: Optional[str] = None


class ProactiveConfig(BaseModel):
    enabled: bool = False


class DashboardConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8787


class MCPConfig(BaseModel):
    enabled: bool = True


class AppConfig(BaseModel):
    workspace: Path = Path("workspace")
    llm: LLMConfig = Field(default_factory=LLMConfig)
    onebot: OneBotConfig = Field(default_factory=OneBotConfig)
    proactive: ProactiveConfig = Field(default_factory=ProactiveConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)


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
