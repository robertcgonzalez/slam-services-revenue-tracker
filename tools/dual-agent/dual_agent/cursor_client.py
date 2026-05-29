"""Client for driving Cursor agents using the official cursor-sdk."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from rich.console import Console

from .config import DualAgentSettings

try:
    from cursor_sdk import Agent, AgentOptions, LocalAgentOptions, CursorAgentError
except ImportError as e:
    raise RuntimeError(
        "cursor-sdk is not installed. Run: pip install cursor-sdk"
    ) from e


@dataclass
class CursorResponse:
    text: str
    agent_id: str | None
    run_id: str | None
    status: str | None  # "finished", "error", etc.
    raw_result: object | None = None


class CursorClient:
    """
    Thin, resilient wrapper around the Cursor Python SDK.

    Uses local runtime (runs on the user's machine against the given cwd).
    """

    def __init__(self, settings: DualAgentSettings, console: Console | None = None):
        self.settings = settings
        self.console = console or Console()
        self._agent = None
        self._agent_id: str | None = None

    def ensure_agent(self, session_id: str | None = None) -> None:
        """Create or resume a Cursor agent for this collaboration."""
        if self._agent is not None:
            return

        opts = AgentOptions(
            api_key=self.settings.cursor_api_key,
            model=self.settings.cursor_model,
            local=LocalAgentOptions(
                cwd=str(self.settings.effective_work_dir),
            ),
        )

        if session_id:
            # Resume existing agent by ID
            try:
                self._agent = Agent.resume(session_id, opts)
                self._agent_id = session_id
                self.console.print(f"[dim]Resumed Cursor agent[/dim] [cyan]{session_id}[/cyan]")
            except Exception as e:
                self.console.print(f"[yellow]Could not resume Cursor agent {session_id}: {e}. Creating new one.[/yellow]")
                self._create_fresh(opts)
        else:
            self._create_fresh(opts)

    def _create_fresh(self, opts: AgentOptions) -> None:
        self._agent = Agent.create(**opts.model_dump() if hasattr(opts, "model_dump") else opts.__dict__)
        # The SDK returns an async context in some versions; we normalize
        if hasattr(self._agent, "__enter__"):
            self._agent = self._agent.__enter__()
        self._agent_id = getattr(self._agent, "agent_id", None) or getattr(self._agent, "id", None)
        self.console.print(f"[dim]Created new Cursor agent[/dim] [cyan]{self._agent_id}[/cyan]")

    def send(
        self,
        prompt: str,
        *,
        system_addendum: str | None = None,
    ) -> CursorResponse:
        """Send a prompt to the Cursor agent and wait for completion."""
        self.ensure_agent()

        full_prompt = prompt
        if system_addendum:
            full_prompt = f"{prompt}\n\n{system_addendum}"

        try:
            run = self._agent.send(full_prompt)  # type: ignore[attr-defined]

            # Collect final text (best effort - SDK surface evolves)
            collected_text = []
            try:
                # Preferred streaming path
                for message in run.messages():
                    if getattr(message, "type", None) == "assistant":
                        for block in getattr(message.message, "content", []):
                            if getattr(block, "type", None) == "text":
                                collected_text.append(getattr(block, "text", ""))
            except Exception:
                # Fallback: some versions expose .wait() + .result
                pass

            result = run.wait() if hasattr(run, "wait") else None

            text = "".join(collected_text) or getattr(result, "result", "") or str(result or "")

            return CursorResponse(
                text=text,
                agent_id=self._agent_id,
                run_id=getattr(result, "id", None) if result else None,
                status=getattr(result, "status", None) if result else "finished",
                raw_result=result,
            )

        except CursorAgentError as e:
            raise RuntimeError(f"Cursor SDK startup error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Cursor agent call failed: {e}") from e

    def send_streaming(
        self,
        prompt: str,
        *,
        system_addendum: str | None = None,
    ) -> Iterator[str]:
        """Yield text chunks as they arrive (best effort)."""
        resp = self.send(prompt, system_addendum=system_addendum)
        if resp.text:
            yield resp.text

    def close(self) -> None:
        if self._agent and hasattr(self._agent, "close"):
            try:
                self._agent.close()
            except Exception:
                pass
        self._agent = None

    @property
    def agent_id(self) -> str | None:
        return self._agent_id

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
