import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from mini_agent.db.migrations import apply_migrations
from mini_agent.llm import ToolCall
from mini_agent.tools.registry import ToolRegistry


class DriftSkill(BaseModel):
    name: str
    path: Path
    instruction: str


class FinishDriftArgs(BaseModel):
    one_line: str
    next: str
    message_result: str


class DriftResult(BaseModel):
    skill_name: str
    status: str
    summary: str
    message_sent: bool = False


class DriftStore:
    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)
        self.db_path = self.workspace / "agent.db"
        apply_migrations(self.db_path)

    def record_run(
        self,
        skill_name: str,
        status: str,
        summary: str,
        message_sent: bool = False,
    ) -> DriftResult:
        self._write_skill_state(skill_name, status)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                insert into drift_runs (finished_at, status, summary)
                values (current_timestamp, ?, ?)
                """,
                (status, f"{skill_name}: {summary}"),
            )
            conn.commit()
        return DriftResult(
            skill_name=skill_name,
            status=status,
            summary=summary,
            message_sent=message_sent,
        )

    def last_run_at(self, skill_name: str) -> Optional[datetime]:
        state_path = self._state_path(skill_name)
        if not state_path.exists():
            return None
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return datetime.fromisoformat(data["last_run_at"])

    def latest_run(self) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                select status, summary from drift_runs
                order by id desc
                limit 1
                """
            ).fetchone()
        if row is None:
            return None
        return {"status": row[0], "summary": row[1]}

    def _write_skill_state(self, skill_name: str, status: str) -> None:
        state_path = self._state_path(skill_name)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "last_run_at": datetime.now(timezone.utc).isoformat(),
                    "status": status,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _state_path(self, skill_name: str) -> Path:
        return self.workspace / "drift" / "skills" / skill_name / "state.json"


class DriftLoop:
    def __init__(
        self,
        workspace: Path,
        llm: Any,
        tools: ToolRegistry,
        store: DriftStore,
        max_steps: int = 8,
        min_interval_minutes: int = 120,
    ) -> None:
        self.workspace = Path(workspace)
        self.llm = llm
        self.tools = tools
        self.store = store
        self.max_steps = max_steps
        self.min_interval_minutes = min_interval_minutes

    async def run_once(self, proactive_pushed: bool) -> Optional[DriftResult]:
        if proactive_pushed:
            return None
        skill = select_least_recently_run(scan_skills(self.workspace), self.store)
        if skill is None or not self._interval_elapsed(skill.name):
            return None

        message_sent = False
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "Run this Drift skill safely. Use at most one message_push "
                    "and call finish_drift before ending."
                ),
            },
            {"role": "user", "content": skill.instruction},
        ]
        schemas = [*self.tools.get_schemas(), _finish_tool_schema()]

        for _ in range(self.max_steps):
            response = await self.llm.chat(messages, schemas)
            if not response.tool_calls:
                messages.append({"role": "assistant", "content": response.content})
                continue
            for tool_call in response.tool_calls:
                if tool_call.name == "finish_drift":
                    args = FinishDriftArgs.model_validate(tool_call.arguments)
                    validate_finish_drift(args, message_sent=message_sent)
                    return self.store.record_run(
                        skill.name,
                        status="finished",
                        summary=args.one_line,
                        message_sent=message_sent,
                    )
                if tool_call.name == "message_push" and message_sent:
                    messages.append(_tool_message(tool_call, {"error": "message_push already used"}))
                    continue
                result = await self.tools.execute(tool_call.name, tool_call.arguments)
                if tool_call.name == "message_push" and result.success:
                    message_sent = True
                messages.append(_tool_message(tool_call, result.model_dump()))

        return self.store.record_run(
            skill.name,
            status="unfinished",
            summary="max steps reached without finish_drift",
            message_sent=message_sent,
        )

    def _interval_elapsed(self, skill_name: str) -> bool:
        if self.min_interval_minutes <= 0:
            return True
        last_run = self.store.last_run_at(skill_name)
        if last_run is None:
            return True
        return datetime.now(timezone.utc) - last_run >= timedelta(
            minutes=self.min_interval_minutes
        )


def scan_skills(workspace: Path) -> List[DriftSkill]:
    skills_dir = Path(workspace) / "drift" / "skills"
    if not skills_dir.exists():
        return []
    skills = []
    for path in sorted(skills_dir.glob("*.md")):
        skills.append(
            DriftSkill(
                name=path.stem,
                path=path,
                instruction=path.read_text(encoding="utf-8"),
            )
        )
    return skills


def select_least_recently_run(
    skills: List[DriftSkill],
    store: DriftStore,
) -> Optional[DriftSkill]:
    if not skills:
        return None

    def key(skill: DriftSkill):
        return store.last_run_at(skill.name) or datetime.min.replace(tzinfo=timezone.utc)

    return sorted(skills, key=key)[0]


def validate_finish_drift(args: FinishDriftArgs, message_sent: bool) -> None:
    if message_sent and args.message_result != "sent":
        raise ValueError("message_result must be 'sent' after message_push")
    if not message_sent and args.message_result == "sent":
        raise ValueError("message_result cannot be 'sent' without message_push")


def _finish_tool_schema() -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "finish_drift",
            "description": "Finish the Drift run with a summary.",
            "parameters": FinishDriftArgs.model_json_schema(),
        },
    }


def _tool_message(tool_call: ToolCall, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }
