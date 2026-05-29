"""Client for driving Cursor agents using the official cursor-sdk.

This version is hardened for reliable bidirectional handoff in long-running
dual-agent collaborations. It prioritizes:
- Correct usage of the public Agent / Run APIs
- Robust final text extraction via wait() + RunResult
- Excellent diagnostics (agent_id, run_id, status on every turn)
- Proper resumption using stored agent_ids
- Clear, actionable error messages
- Windows bridge compatibility shims (get_blocking / set_blocking)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from rich.console import Console

from .config import DualAgentSettings

try:
    from cursor_sdk import (
        Agent,
        AgentOptions,
        CursorAgentError,
        LocalAgentOptions,
    )
except ImportError as e:
    raise RuntimeError(
        "cursor-sdk is not installed. Run: pip install cursor-sdk"
    ) from e


# --- Windows + Cursor SDK bridge compatibility shim ---
# Some versions of the cursor-sdk bridge use os.get_blocking / os.set_blocking
# on pipe fds, which is not available on all Windows Python versions (3.10/3.14).
# We provide safe fallbacks before the SDK imports the bridge.
import os as _os
if not hasattr(_os, "get_blocking"):
    def _safe_get_blocking(fd):
        return True
    _os.get_blocking = _safe_get_blocking  # type: ignore[attr-defined]
if not hasattr(_os, "set_blocking"):
    def _safe_set_blocking(fd, blocking):
        pass
    _os.set_blocking = _safe_set_blocking  # type: ignore[attr-defined]
# --- end shim ---


@dataclass
class CursorResponse:
    """Normalized response from a Cursor agent turn."""
    text: str
    agent_id: str | None
    run_id: str | None
    status: str | None  # finished, error, cancelled, etc.
    raw_result: object | None = None
    duration_ms: int | None = None


class CursorClient:
    """
    Resilient wrapper around the Cursor Python SDK for autonomous
    Grok ↔ Cursor collaboration loops.

    Key improvements:
    - Uses the documented public API (Agent.create / resume / send / wait)
    - Robust final text extraction via wait() + RunResult.result
    - Excellent diagnostics (agent_id, run_id, status on every turn)
    - Proper agent resumption using the agent_id from previous successful turns
    - Context manager support and safe close()
    - Preserved Windows bridge shims for 3.10/3.14 compatibility
    """

    def __init__(self, settings: DualAgentSettings, console: Console | None = None):
        self.settings = settings
        self.console = console or Console()
        self._agent: Agent | None = None
        self._agent_id: str | None = None
        self._last_run_id: str | None = None

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def ensure_agent(self, preferred_agent_id: str | None = None) -> None:
        """Create a fresh Cursor agent or resume an existing one.

        We prefer resuming using the agent_id stored from a previous
        successful turn (passed in via the collaboration session).
        """
        if self._agent is not None:
            return

        local_opts = LocalAgentOptions(
            cwd=str(self.settings.effective_work_dir),
        )

        # Best-effort yolo support: when yolo_cursor is true we try to relax sandbox
        # (exact semantics depend on the Cursor desktop + SDK version).
        if getattr(self.settings, "yolo_cursor", False):
            try:
                from cursor_sdk import SandboxOptions
                local_opts.sandbox_options = SandboxOptions(enabled=False)  # type: ignore[attr-defined]
            except Exception:
                pass

        # Build options with api_key at construction time (most reliable across SDK versions)
        opts_kwargs = {
            "model": self.settings.cursor_model,
            "local": local_opts,
        }
        if self.settings.cursor_api_key:
            opts_kwargs["api_key"] = self.settings.cursor_api_key

        opts = AgentOptions(**opts_kwargs)

        target_id = preferred_agent_id or self._agent_id

        if target_id:
            try:
                self._agent = Agent.resume(target_id, opts)
                self._agent_id = target_id
                self.console.print(
                    f"[dim]Resumed Cursor agent[/dim] [cyan]{target_id}[/cyan]"
                )
                return
            except Exception as e:
                self.console.print(
                    f"[yellow]Resume of Cursor agent {target_id} failed: {e}. "
                    "Falling back to fresh agent.[/yellow]"
                )

        # Fresh agent
        self._create_fresh(opts)

    def _create_fresh(self, opts: AgentOptions) -> None:
        """Create a brand new Cursor agent."""
        try:
            # Correct public API usage
            self._agent = Agent.create(opts)
        except Exception as e:
            # Some SDK versions return an async context; try to normalize
            if hasattr(Agent, "create"):
                try:
                    created = Agent.create(opts)
                    if hasattr(created, "__enter__"):
                        self._agent = created.__enter__()
                    else:
                        self._agent = created
                except Exception as inner:
                    raise RuntimeError(
                        f"Failed to create Cursor agent: {inner}"
                    ) from e
            else:
                raise RuntimeError(f"Failed to create Cursor agent: {e}") from e

        # Capture the authoritative agent_id returned by the SDK
        self._agent_id = getattr(self._agent, "agent_id", None) or getattr(self._agent, "id", None)

        if self._agent_id:
            self.console.print(
                f"[dim]Created new Cursor agent[/dim] [bold cyan]{self._agent_id}[/bold cyan]"
            )
        else:
            self.console.print("[yellow]Created Cursor agent (no agent_id surfaced)[/yellow]")

    # ------------------------------------------------------------------
    # Core send operation (the actual handoff)
    # ------------------------------------------------------------------

    def send(
        self,
        prompt: str,
        *,
        system_addendum: str | None = None,
        preferred_agent_id: str | None = None,
    ) -> CursorResponse:
        """Send a prompt to Cursor and block until we have a terminal result.

        This is the critical handoff method. It must be extremely reliable.
        """
        self.ensure_agent(preferred_agent_id=preferred_agent_id)

        if self._agent is None:
            raise RuntimeError("Cursor agent is not initialized")

        full_prompt = prompt
        if system_addendum:
            full_prompt = f"{prompt}\n\n{system_addendum}"

        self.console.print("[dim]Sending turn to Cursor agent...[/dim]")

        try:
            # Start the run
            run = self._agent.send(full_prompt)

            # Capture run identity immediately
            run_id = getattr(run, "id", None) or getattr(run, "run_id", None)
            self._last_run_id = run_id

            self.console.print(
                f"[dim]Cursor run started[/dim] "
                f"[cyan]{run_id or 'unknown-run-id'}[/cyan]"
            )

            # Block for completion using the stable wait() path
            result = run.wait() if hasattr(run, "wait") else None

            # Best-effort text extraction
            text = ""
            status = "unknown"
            duration_ms = None

            if result is not None:
                # RunResult has .result (the final assistant text)
                text = getattr(result, "result", "") or getattr(result, "text", "") or ""
                status = getattr(result, "status", None) or "finished"
                duration_ms = getattr(result, "duration_ms", None)

                # Fallbacks for different SDK shapes
                if not text:
                    text = str(getattr(result, "output", "") or "")

            # If wait() didn't give us text, try the convenience method
            if not text and hasattr(run, "text"):
                try:
                    text = run.text() or text
                except Exception:
                    pass

            # Final safety net
            if not text:
                # Last resort: try to pull from conversation or raw
                try:
                    conv = run.conversation() if hasattr(run, "conversation") else []
                    for turn in reversed(conv or []):
                        if getattr(turn, "role", "") == "assistant":
                            text = getattr(turn, "content", "") or ""
                            break
                except Exception:
                    pass

            if not text:
                text = "[Cursor returned no text for this turn]"

            self.console.print(
                f"[dim]Cursor turn complete[/dim] "
                f"status=[green]{status}[/green] "
                f"run=[cyan]{run_id or 'n/a'}[/cyan]"
            )

            return CursorResponse(
                text=text,
                agent_id=self._agent_id,
                run_id=run_id,
                status=status,
                raw_result=result,
                duration_ms=duration_ms,
            )

        except CursorAgentError as e:
            self.console.print(f"[bold red]CursorAgentError during send:[/bold red] {e}")
            raise RuntimeError(f"Cursor SDK error: {e}") from e

        except Exception as e:
            self.console.print(f"[bold red]Unexpected error in Cursor handoff:[/bold red] {e}")
            # Include as much context as possible
            raise RuntimeError(
                f"Cursor agent call failed (agent_id={self._agent_id}, last_run={self._last_run_id}): {e}"
            ) from e

    def send_streaming(
        self,
        prompt: str,
        *,
        system_addendum: str | None = None,
    ) -> Iterator[str]:
        """Best-effort streaming (falls back to full send)."""
        resp = self.send(prompt, system_addendum=system_addendum)
        if resp.text:
            yield resp.text

    # ------------------------------------------------------------------
    # Diagnostics & cleanup
    # ------------------------------------------------------------------

    def diagnostic_info(self) -> dict:
        """Return current state for debugging handoff issues."""
        return {
            "has_agent": self._agent is not None,
            "agent_id": self._agent_id,
            "last_run_id": self._last_run_id,
            "model": self.settings.cursor_model,
            "work_dir": str(self.settings.effective_work_dir),
        }

    def close(self) -> None:
        """Safely close the underlying Cursor agent if supported."""
        if self._agent and hasattr(self._agent, "close"):
            try:
                self._agent.close()
                self.console.print("[dim]Closed Cursor agent[/dim]")
            except Exception as e:
                self.console.print(f"[yellow]Error closing Cursor agent: {e}[/yellow]")
        self._agent = None
        self._agent_id = None

    @property
    def agent_id(self) -> str | None:
        return self._agent_id

    @property
    def last_run_id(self) -> str | None:
        return self._last_run_id

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
