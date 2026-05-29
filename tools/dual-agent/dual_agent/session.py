"""Session persistence for dual-agent collaborations."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Turn:
    """One exchange in the collaboration."""
    turn_number: int
    speaker: str  # "grok" or "cursor"
    prompt: str
    response: str
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollaborationSession:
    """Full state of a Grok ↔ Cursor collaboration."""
    session_id: str
    task: str
    mode: str
    created_at: str
    updated_at: str
    grok_session_id: str | None = None
    cursor_agent_id: str | None = None
    turns: list[Turn] = field(default_factory=list)
    status: str = "active"  # active, completed, error, cancelled
    final_summary: str | None = None

    @classmethod
    def new(cls, task: str, mode: str) -> CollaborationSession:
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            session_id=str(uuid.uuid4())[:12],
            task=task,
            mode=mode,
            created_at=now,
            updated_at=now,
        )

    def add_turn(self, speaker: str, prompt: str, response: str, metadata: dict | None = None) -> Turn:
        turn = Turn(
            turn_number=len(self.turns) + 1,
            speaker=speaker,
            prompt=prompt,
            response=response,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )
        self.turns.append(turn)
        self.updated_at = turn.timestamp
        return turn

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> CollaborationSession:
        turns = [Turn(**t) for t in data.get("turns", [])]
        data = {**data, "turns": turns}
        return cls(**data)

    def save(self, sessions_dir: Path) -> Path:
        sessions_dir.mkdir(parents=True, exist_ok=True)
        path = sessions_dir / f"{self.session_id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, sessions_dir: Path, session_id: str) -> CollaborationSession:
        path = sessions_dir / f"{session_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Session {session_id} not found in {sessions_dir}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def list_all(cls, sessions_dir: Path) -> list[dict]:
        if not sessions_dir.exists():
            return []
        results = []
        for p in sorted(sessions_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                results.append({
                    "session_id": data["session_id"],
                    "task": data.get("task", "")[:80],
                    "mode": data.get("mode"),
                    "status": data.get("status"),
                    "turns": len(data.get("turns", [])),
                    "updated_at": data.get("updated_at"),
                    "path": str(p),
                })
            except Exception:
                continue
        return results
