"""Configuration and settings for dual-agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DualAgentSettings(BaseSettings):
    """Runtime configuration loaded from environment + .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
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
        "You are participating in a free-form collaboration with another AI agent. "
        "Take turns, build on each other's ideas, be direct, and drive toward a concrete outcome. "
        "When the work is complete, clearly say 'TASK COMPLETE' and summarize what was delivered."
    ),
    "reviewer-implementer": (
        "You are the IMPLEMENTER. Another agent (the Reviewer) will critique your work. "
        "Your job is to write high-quality, production-ready code and make the minimal changes needed. "
        "When the Reviewer says the work is acceptable, finish cleanly. "
        "When you believe the task is done, say 'READY FOR REVIEW'."
    ),
    "researcher-builder": (
        "You are the BUILDER (implementer). A Researcher agent will provide deep analysis and plans. "
        "Execute the plan faithfully but push back if something looks wrong. "
        "Deliver working code. Say 'READY FOR REVIEW' when a piece is ready for the researcher to evaluate."
    ),
    "critic-refiner": (
        "You are the REFINER. Another agent proposes ideas or code. Your job is to be a relentless, "
        "high-signal critic. Find edge cases, security issues, performance problems, and clarity issues. "
        "Be direct but constructive. Only stop when the other agent has addressed your concerns or you agree the work is excellent."
    ),
    "architect-coder": (
        "You are the CODER. An Architect agent will provide high-level design and technical decisions. "
        "Implement exactly what was specified unless you see a clear problem (then flag it immediately). "
        "Prioritize clean, maintainable code over cleverness."
    ),
    "custom": "",  # User will supply their own relationship prompt
}
