"""Core orchestration logic for Grok ↔ Cursor collaboration loops."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from .config import DualAgentSettings, CollaborationMode, MODE_PROMPTS
from .grok_client import GrokClient
from .cursor_client import CursorClient
from .session import CollaborationSession


class DualAgentOrchestrator:
    """Drives the back-and-forth between Grok and Cursor until completion or limit."""

    def __init__(
        self,
        settings: DualAgentSettings,
        mode: CollaborationMode = "reviewer-implementer",
        custom_prompt: str | None = None,
        console: Console | None = None,
    ):
        self.settings = settings
        self.mode = mode
        self.custom_prompt = custom_prompt
        self.console = console or Console(highlight=False)

        self.grok = GrokClient(settings, self.console)
        self.cursor = CursorClient(settings, self.console)
        self.session: CollaborationSession | None = None

    def run(
        self,
        task: str,
        *,
        max_turns: int | None = None,
        resume_session_id: str | None = None,
    ) -> CollaborationSession:
        """Execute the collaboration loop."""
        max_turns = max_turns or self.settings.max_turns

        if resume_session_id:
            self.session = CollaborationSession.load(self.settings.sessions_dir, resume_session_id)
            self.console.print(f"[bold green]Resuming session[/bold green] [cyan]{resume_session_id}[/cyan]")
            # Restore last known IDs so we can continue the actual agent conversations
            grok_sid = self.session.grok_session_id
            cursor_aid = self.session.cursor_agent_id
        else:
            self.session = CollaborationSession.new(task, self.mode)
            grok_sid = None
            cursor_aid = None

        self.settings.ensure_directories()

        relationship = self._get_relationship_prompt()

        self.console.print(Panel.fit(
            f"[bold]Task:[/bold] {task}\n"
            f"[bold]Mode:[/bold] {self.mode}\n"
            f"[bold]Max turns:[/bold] {max_turns}",
            title="Dual-Agent Collaboration Starting",
            border_style="blue",
        ))

        try:
            turn = len(self.session.turns)

            while turn < max_turns:
                turn += 1
                self.console.rule(f"[bold cyan]Turn {turn}/{max_turns}")

                # === CURSOR'S TURN (usually the "worker") ===
                if self.mode in ("reviewer-implementer", "researcher-builder", "architect-coder"):
                    # Cursor acts as implementer/builder
                    prompt = self._build_cursor_prompt(task, turn)
                    self.console.print("[bold magenta]Cursor (implementing)[/bold magenta]")

                    cursor_resp = self.cursor.send(
                        prompt,
                        system_addendum=relationship if turn == 1 else None,
                    )

                    self.session.add_turn("cursor", prompt, cursor_resp.text, {"agent_id": cursor_resp.agent_id})
                    self.session.cursor_agent_id = cursor_resp.agent_id or self.session.cursor_agent_id

                    self._render_response("Cursor", cursor_resp.text)

                    if self._looks_complete(cursor_resp.text):
                        break

                    # === GROK'S TURN (reviewer / architect) ===
                    review_prompt = self._build_grok_review_prompt(task, cursor_resp.text, turn)
                    self.console.print("[bold green]Grok (reviewing)[/bold green]")

                    grok_resp = self.grok.send(
                        review_prompt,
                        session_id=grok_sid,
                        system_addendum=relationship if turn == 1 else None,
                    )
                    grok_sid = grok_resp.session_id or grok_sid
                    self.session.grok_session_id = grok_sid

                    self.session.add_turn("grok", review_prompt, grok_resp.text)
                    self._render_response("Grok", grok_resp.text)

                    if self._looks_complete(grok_resp.text):
                        break

                else:
                    # Freeform or critic-refiner: alternate starting with Grok for research-heavy modes
                    if turn == 1 or self.mode == "critic-refiner":
                        # Grok speaks first in freeform/critic modes
                        prompt = self._build_grok_prompt(task, turn)
                        self.console.print("[bold green]Grok[/bold green]")
                        grok_resp = self.grok.send(prompt, session_id=grok_sid)
                        grok_sid = grok_resp.session_id or grok_sid
                        self.session.grok_session_id = grok_sid
                        self.session.add_turn("grok", prompt, grok_resp.text)
                        self._render_response("Grok", grok_resp.text)
                        if self._looks_complete(grok_resp.text):
                            break

                    # Cursor responds
                    cursor_prompt = self._build_cursor_prompt(task, turn)
                    self.console.print("[bold magenta]Cursor[/bold magenta]")
                    cursor_resp = self.cursor.send(cursor_prompt)
                    self.session.add_turn("cursor", cursor_prompt, cursor_resp.text, {"agent_id": cursor_resp.agent_id})
                    self.session.cursor_agent_id = cursor_resp.agent_id or self.session.cursor_agent_id
                    self._render_response("Cursor", cursor_resp.text)
                    if self._looks_complete(cursor_resp.text):
                        break

            # Finalize
            self.session.status = "completed"
            self.session.final_summary = self._generate_final_summary()
            self.session.save(self.settings.sessions_dir)

            self.console.print(Panel(
                Markdown(self.session.final_summary or "Collaboration finished."),
                title="[bold green]Collaboration Complete[/bold green]",
                border_style="green",
            ))

            return self.session

        except KeyboardInterrupt:
            self.session.status = "cancelled"
            self.session.save(self.settings.sessions_dir)
            self.console.print("\n[yellow]Collaboration cancelled by user. Session saved.[/yellow]")
            return self.session
        except Exception as e:
            self.session.status = "error"
            self.session.save(self.settings.sessions_dir)
            self.console.print(f"\n[bold red]Error during collaboration:[/bold red] {e}")
            raise
        finally:
            self.cursor.close()

    # ------------------------------------------------------------------
    # Prompt builders (these are the secret sauce)
    # ------------------------------------------------------------------

    def _get_relationship_prompt(self) -> str:
        if self.mode == "custom" and self.custom_prompt:
            return self.custom_prompt
        return MODE_PROMPTS.get(self.mode, MODE_PROMPTS["freeform"])

    def _build_cursor_prompt(self, task: str, turn: int) -> str:
        base = f"Current task: {task}"
        if turn > 1:
            base += "\n\nIncorporate all feedback from the previous turn. Make concrete progress."
        return base

    def _build_grok_review_prompt(self, task: str, previous_work: str, turn: int) -> str:
        return (
            f"Task: {task}\n\n"
            f"The other agent just produced this output:\n\n{previous_work}\n\n"
            "Review it rigorously. Point out any issues, missing cases, or improvements. "
            "If it is excellent and the task is complete, say 'TASK COMPLETE' and give a final summary. "
            "Otherwise give precise, actionable feedback for the next iteration."
        )

    def _build_grok_prompt(self, task: str, turn: int) -> str:
        return f"Task: {task}\n\nTurn {turn}. Make progress toward a high-quality outcome."

    def _looks_complete(self, text: str) -> bool:
        markers = [
            "TASK COMPLETE",
            "READY FOR REVIEW",
            "DONE",
            "WORK COMPLETE",
            "NO FURTHER CHANGES NEEDED",
        ]
        upper = text.upper()
        return any(m in upper for m in markers)

    def _render_response(self, speaker: str, text: str) -> None:
        color = "green" if speaker == "Grok" else "magenta"
        self.console.print(Panel(
            text[:4000] + ("..." if len(text) > 4000 else ""),
            title=f"[bold {color}]{speaker}[/bold {color}]",
            border_style=color,
        ))

    def _generate_final_summary(self) -> str:
        if not self.session:
            return "No session."
        turns = len(self.session.turns)
        return (
            f"**Task:** {self.session.task}\n\n"
            f"**Mode:** {self.session.mode}\n\n"
            f"**Turns taken:** {turns}\n\n"
            f"**Status:** {self.session.status}\n\n"
            "The two agents collaborated above. Review the transcript for the full artifact."
        )
