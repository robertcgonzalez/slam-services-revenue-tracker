"""Client for driving Grok via headless mode with full session support."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from rich.console import Console

from .config import DualAgentSettings


@dataclass
class GrokResponse:
    text: str
    session_id: str | None
    stop_reason: str | None
    raw: dict


class GrokClient:
    """Wrapper around the `grok` CLI in headless mode."""

    def __init__(self, settings: DualAgentSettings, console: Console | None = None):
        self.settings = settings
        self.console = console or Console()
        self._last_session_id: str | None = None

    def send(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        resume: bool = False,
        system_addendum: str | None = None,
    ) -> GrokResponse:
        """
        Send a prompt to Grok headless and return the structured result.

        Args:
            prompt: The user message / instructions.
            session_id: Existing session to continue.
            resume: If True, use --resume instead of -s.
            system_addendum: Extra instructions appended to this turn only.
        """
        full_prompt = prompt
        if system_addendum:
            full_prompt = f"{prompt}\n\n---\nAdditional context / instructions:\n{system_addendum}"

        cmd = self._build_command(full_prompt, session_id=session_id, resume=resume)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.settings.grok_timeout,
                cwd=self.settings.effective_work_dir,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Grok call timed out after {self.settings.grok_timeout}s") from None

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            raise RuntimeError(
                f"Grok CLI failed (exit {result.returncode})\n"
                f"stderr: {stderr}\nstdout: {stdout[:2000]}"
            )

        # Parse JSON output
        try:
            data = json.loads(result.stdout.strip())
        except json.JSONDecodeError as e:
            # Sometimes grok prints extra stuff; try to recover last JSON object
            lines = [l for l in result.stdout.strip().splitlines() if l.strip().startswith("{")]
            if lines:
                data = json.loads(lines[-1])
            else:
                raise RuntimeError(f"Failed to parse Grok JSON output: {e}\nOutput was:\n{result.stdout[:3000]}") from e

        text = data.get("text", "") or data.get("result", "")
        sid = data.get("sessionId") or data.get("session_id")
        stop = data.get("stopReason") or data.get("stop_reason")

        self._last_session_id = sid

        return GrokResponse(
            text=text,
            session_id=sid,
            stop_reason=stop,
            raw=data,
        )

    def send_streaming(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        system_addendum: str | None = None,
    ) -> Iterator[str]:
        """
        Stream text chunks from Grok (useful for live UI).
        Falls back to non-streaming if streaming-json has issues.
        """
        # For simplicity and reliability we use the non-streaming path and yield the whole thing.
        # Streaming-json is more fragile across versions.
        resp = self.send(prompt, session_id=session_id, system_addendum=system_addendum)
        if resp.text:
            yield resp.text

    def _build_command(
        self,
        prompt: str,
        *,
        session_id: str | None,
        resume: bool,
    ) -> list[str]:
        cmd = ["grok", "-p", prompt, "--output-format", "json"]

        if self.settings.grok_model:
            cmd += ["-m", self.settings.grok_model]

        if self.settings.yolo_grok:
            cmd.append("--yolo")

        cwd = str(self.settings.effective_work_dir)
        cmd += ["--cwd", cwd]

        if session_id:
            if resume:
                cmd += ["--resume", session_id]
            else:
                cmd += ["-s", session_id]

        return cmd

    @property
    def last_session_id(self) -> str | None:
        return self._last_session_id
