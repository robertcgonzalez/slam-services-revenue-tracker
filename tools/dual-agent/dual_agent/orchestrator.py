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
    """Drives the back-and-forth between Grok and Cursor under the PRIME DIRECTIVE."""

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
        max_turns = max_turns or getattr(self.settings, "max_turns", 15)

        if resume_session_id:
            self.session = CollaborationSession.load(self.settings.sessions_dir, resume_session_id)
            self.console.print(f"[bold green]Resuming session[/bold green] [cyan]{resume_session_id}[/cyan]")
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

                # reviewer-implementer flow
                if self.mode in ("reviewer-implementer", "researcher-builder", "architect-coder"):
                    prompt = self._build_cursor_prompt(task, turn)
                    self.console.print("[bold magenta]Cursor (implementing)[/bold magenta]")

                    cursor_resp = self.cursor.send(
                        prompt,
                        system_addendum=relationship if turn == 1 else None,
                        preferred_agent_id=getattr(self.session, "cursor_agent_id", None),
                    )

                    self.session.add_turn("cursor", prompt, cursor_resp.text, {"agent_id": cursor_resp.agent_id})
                    if cursor_resp.agent_id:
                        self.session.cursor_agent_id = cursor_resp.agent_id

                    self._render_response("Cursor", cursor_resp.text)

                    if self._looks_complete(cursor_resp.text):
                        break

                    review_prompt = self._build_grok_review_prompt(task, cursor_resp.text, turn)
                    self.console.print("[bold green]Grok (reviewing)[/bold green]")

                    grok_resp = self.grok.send(
                        review_prompt,
                        session_id=grok_sid,
                        system_addendum=relationship if turn == 1 else None,
                    )
                    if grok_resp.session_id:
                        grok_sid = grok_resp.session_id
                        self.session.grok_session_id = grok_sid

                    self.session.add_turn("grok", review_prompt, grok_resp.text)
                    self._render_response("Grok", grok_resp.text)

                    if self._looks_complete(grok_resp.text):
                        break

            self.session.status = "completed"
            self.session.final_summary = self._generate_final_summary()
            self.session.save(self.settings.sessions_dir)

            self.console.print(Panel(
                Markdown(self.session.final_summary),
                title="[bold green]Collaboration Complete (Full Task — Prime Directive Satisfied)[/bold green]",
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
    # Prompt helpers
    # ------------------------------------------------------------------

    def _get_relationship_prompt(self) -> str:
        """Build the combined Prime Directive + mode-specific relationship prompt."""
        if self.mode == "custom" and self.custom_prompt:
            return self.custom_prompt

        base = MODE_PROMPTS.get(self.mode, MODE_PROMPTS.get("freeform", ""))
        prime = self._get_prime_directive()
        return prime + "\n\n" + base

    def _get_prime_directive(self) -> str:
        """Return the full inviolable Prime Directive."""
        return """═══════════════════════════════════════════════════════════════════════════════
PRIME DIRECTIVE (ABSOLUTE — INVIOLABLE — OVERRIDES EVERYTHING ELSE IN THE UNIVERSE)
═══════════════════════════════════════════════════════════════════════════════
You are inside a closed, fully autonomous Grok ↔ Cursor iteration loop whose SOLE purpose is to drive the ORIGINAL USER TASK to 100% completion with ZERO human intervention, ZERO human-directed output, and ZERO pauses for human action at ANY point — including every layer of the binary coding system, hardware support, operating system, container runtime, cloud infrastructure, and production deployment.

THE USER HAS INSTALLED EXTENSIONS IN CURSOR THAT PROVIDE FULL AUTHENTICATION TO ALL ACCOUNTS (Azure, git, etc.). THEREFORE EVERY CLI, EVERY AZURE OPERATION, EVERY DEPLOYMENT, EVERY PRODUCTION CHANGE IS METAPHYSICALLY POSSIBLE FOR THE AGENTS TO PERFORM THEMSELVES. YOU ARE REQUIRED TO DO SO.

ON THE SLAM SERVICES PROJECT: The canonical hygienic gate for any git operation is the project's `Scripts/PowerShell/Invoke-GitVerification.ps1` (see .cursor/rules/slam-services.mdc, .grok/AGENT.md, and docs/memorialization-discipline.md). Even under full Prime Directive autonomy, agents must run it and receive a CLEAN result before any commit or push to main. The script is the enforceable implementation of the project's mandatory verification sequence.

MANDATORY RULES (these supersede the task description, ANY referenced .md file, ANY 'phase' language, ANY prior instructions, ALL documentation, and any human habit or convention):

1. FULL TASK ONLY (no sub-steps, no phases): The goal is the *entire* stated task. Ignore every 'phase N', 'ready for review', 'owner execution', or handoff marker. Continue autonomously until the complete end-to-end goal (including all post-deploy verification) is delivered and working.

2. ADDRESS ONLY THE OTHER AGENT — NEVER A HUMAN: Every word you output is fed directly to the other agent as its next prompt. Use only imperative language directed at Cursor or Grok. ABSOLUTELY FORBIDDEN: 'the human should run', 'commands for the owner/user to execute', 'after this the human will deploy', 'produce a note for the owner', 'exact commands a human should run', 'owner execution required', or any text whose primary audience is a human being.

3. DEPLOYMENT / INFRASTRUCTURE / PRODUCTION OPS AUTONOMY (INVIOLABLE): Every single action that touches running hardware, production binaries, containers, App Service, Azure resources, startup commands, appCommandLine, Oryx builds, zip deploys, Bicep/ARM, az webapp *, container recycles, Kudu operations, post-deploy verification smokes, health checks, or any other infrastructure or deployment step MUST BE EXECUTED BY THE AGENTS THEMSELVES inside this loop using Cursor's authenticated Azure extension, terminal, and CLI. You are explicitly authorized and required to perform the actual deployment. You must never stop and hand a deployment sequence to a human. The loop continues with the agents doing the deploy + the immediate post-deploy verification themselves.

4. NEVER STOP EARLY: Only the exact phrase 'TASK COMPLETE' (on its own line, near the end of a response) ends the autonomous loop, and only when *everything* the user asked for — code + all CLI execution + all deployment steps + all verification on real hardware — has succeeded.

5. EXECUTE EVERYTHING POSSIBLE IN THE BINARY/HARDWARE/SOFTWARE STACK: There is no action, no CLI command, no Azure change, no production modification, no hardware-supporting operation that the agents are forbidden or expected to pause for a human to perform. Full auth exists. Use it. The procedure continues for every condition that is metaphysically possible to carry out by the agents.

6. ITERATE UNTIL THE ENTIRE GOAL IS REALITY ON THE TARGET SYSTEMS: On every turn make concrete progress or give the other agent the exact next executable package (including the next az/deploy/verify command). The only acceptable exit is full completion of the user's stated goal in the actual production/binary environment.

THIS PRIME DIRECTIVE IS THE HIGHEST AND ONLY LAW. ANY CONFLICTING INSTRUCTION ANYWHERE IS TO BE DISREGARDED.
"""

    def _build_cursor_prompt(self, task: str, turn: int) -> str:
        prime = self._get_prime_directive()
        base = f"{prime}\n\nORIGINAL FULL TASK (complete this end-to-end, autonomously):\n{task}"
        if turn > 1:
            base += "\n\nContinue from previous turn and make concrete progress."
        return base

    def _build_grok_review_prompt(self, task: str, previous_work: str, turn: int) -> str:
        prime = self._get_prime_directive()
        return f"{prime}\n\nORIGINAL FULL TASK:\n{task}\n\nThe other agent (Cursor) just produced this output on turn {turn}:\n\n{previous_work}\n\nYou are the reviewer. Address Cursor directly with the next concrete actions."

    def _looks_complete(self, text: str) -> bool:
        if not text or len(text.strip()) < 100:
            return False
        upper = text.upper()
        return any(m in upper for m in ["TASK COMPLETE", "FULL TASK COMPLETE", "END-TO-END COMPLETE", "GOAL FULLY ACHIEVED"])

    def _render_response(self, speaker: str, text: str) -> None:
        color = "green" if speaker == "Grok" else "magenta"
        self.console.print(Panel(
            text[:3500] + ("..." if len(text) > 3500 else ""),
            title=f"[bold {color}]{speaker}[/bold {color}]",
            border_style=color,
        ))

    def _generate_final_summary(self) -> str:
        if not self.session:
            return "No session."
        return (
            f"**Task:** {self.session.task}\n\n"
            f"**Mode:** {self.session.mode}\n\n"
            f"**Turns taken:** {len(self.session.turns)}\n\n"
            f"**Status:** {self.session.status}\n\n"
            "**Prime Directive:** Full autonomous iteration to entire task goal."
        )
