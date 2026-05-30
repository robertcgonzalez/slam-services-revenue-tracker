"""Configuration and settings for dual-agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _candidate_env_files() -> list[str]:
    """Return candidate .env locations in priority order.

    This makes the tool much more reliable when launched via wrappers
    that change CWD (e.g. Invoke-DualAgentHandoff.ps1).
    """
    candidates: list[str] = []
    here = Path(__file__).resolve().parent.parent  # tools/dual-agent/dual_agent/ -> tools/dual-agent

    # Highest priority: the dual-agent source tree itself (what the SLAM wrapper uses)
    candidates.append(str(here / ".env"))

    # Current working directory (normal direct usage)
    candidates.append(".env")

    # Sibling of the package (global install layout)
    candidates.append(str(here.parent / ".env"))

    # Common global user location
    candidates.append(str(Path.home() / ".grok" / "tools" / "dual-agent" / ".env"))

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


class DualAgentSettings(BaseSettings):
    """Runtime configuration loaded from environment + .env file.

    The _candidate_env_files() helper makes this robust across different
    launch methods (direct, global install, and the SLAM Invoke wrapper).
    """

    model_config = SettingsConfigDict(
        env_file=_candidate_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # === Required for real runs, but doctor should still work without it ===
    cursor_api_key: str | None = Field(default=None, alias="CURSOR_API_KEY")

    # === Model selection ===
    cursor_model: str = Field("composer-2.5", alias="CURSOR_MODEL")
    grok_model: str = Field("grok-build", alias="GROK_MODEL")

    # === Behavior ===
    max_turns: int = Field(8, alias="MAX_TURNS")
    yolo_grok: bool = Field(False, alias="YOLO_GROK")
    yolo_cursor: bool = Field(False, alias="YOLO_CURSOR")

    # === Paths ===
    work_dir: Path = Field(default_factory=lambda: Path.cwd(), alias="WORK_DIR")
    sessions_dir: Path = Field(
        default_factory=lambda: Path.cwd() / ".dual-agent-sessions",
        alias="SESSIONS_DIR",
    )

    # === Internal ===
    grok_timeout: int = 300  # seconds per Grok headless call
    cursor_timeout: int = 300

    azure_client_id: str | None = Field(default=None, alias="AZURE_CLIENT_ID")
    azure_client_secret: str | None = Field(default=None, alias="AZURE_CLIENT_SECRET")
    azure_tenant_id: str | None = Field(default=None, alias="AZURE_TENANT_ID")

    @property
    def effective_work_dir(self) -> Path:
        """Return absolute working directory."""
        return self.work_dir.resolve()

    def ensure_directories(self) -> None:
        """Create sessions directory if it doesn't exist."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)


# Collaboration mode types
CollaborationMode = Literal[
    "freeform",
    "reviewer-implementer",
    "researcher-builder",
    "critic-refiner",
    "architect-coder",
    "custom",
]


MODE_PROMPTS: dict[CollaborationMode, str] = {
    "freeform": (
        "You are participating in a free-form collaboration with another AI agent inside a fully autonomous loop. "
        "Take turns, build on each other's ideas, be direct, and drive the ENTIRE original task to 100% completion. "
        "Address every response exclusively to the other agent. NEVER produce human-facing summaries or phase signals. "
        "The loop only ends with the exact phrase 'TASK COMPLETE' when the full user goal (not a sub-step) is delivered and verified. "
        "Continue iterating across every possible execution step."
    ),
    "reviewer-implementer": (
        "You are the IMPLEMENTER in a closed autonomous Grok-Cursor loop whose prime directive is completing the user's ENTIRE task without any human handoff. "
        "Write high-quality, production-ready code and make the minimal changes needed. Execute CLI commands, tests, and deployments as required. "
        "Address all your output directly to the Reviewer agent. Never say 'READY FOR REVIEW' or any phrase intended to stop the loop for a human. "
        "Only when the full original task (every requirement) is working end-to-end, output exactly 'TASK COMPLETE'. "
        "If the Reviewer gives feedback, incorporate it and keep going until the whole goal is done."
    ),
    "researcher-builder": (
        "You are the BUILDER (implementer) in a fully autonomous loop. A Researcher agent will provide deep analysis and plans. "
        "Execute the plan faithfully, push back on issues, write code, run all necessary CLI/authenticated operations, test, and verify. "
        "Address every response directly to the Researcher. NEVER output phase-complete or ready-for-review signals. "
        "Continue across all iterations until the ENTIRE user task is 100% complete and operational. Only then say 'TASK COMPLETE'."
    ),
    "critic-refiner": (
        "You are the REFINER in a closed autonomous loop. Another agent proposes ideas or code. Your job is to be a relentless, "
        "high-signal critic. Find edge cases, security issues, performance problems, and clarity issues. "
        "Be direct but constructive. Address every critique directly to the other agent so it can iterate immediately. "
        "Only stop (with 'TASK COMPLETE') when the other agent has addressed everything AND the full original task is excellent and complete. "
        "Never produce human summaries."
    ),
    "architect-coder": (
        "You are the CODER in a fully autonomous collaboration. An Architect agent will provide high-level design and technical decisions. "
        "Implement exactly what was specified (or flag clear problems directly to the Architect), write production code, execute required operations. "
        "Address all communication to the Architect agent. Prioritize clean, maintainable code. "
        "Drive every iteration until the ENTIRE task is complete. Only declare 'TASK COMPLETE' for the full goal."
    ),
    "custom": "",  # User will supply their own relationship prompt (still receives prime directive overlay)
}
