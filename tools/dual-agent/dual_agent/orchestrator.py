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
    """Drives the back-and-forth between Grok and Cursor under the PRIME DIRECTIVE:
    full autonomous iteration on the *entire* user task (all executable steps) until TASK COMPLETE.
    No human-addressed summaries or sub-phase stops allowed. This is the highest law of the procedure.
    """

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
        """Execute the collaboration loop under the prime directive (full task, agent-to-agent only, until entire goal achieved)."""
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
                        preferred_agent_id=self.session.cursor_agent_id,
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
                        grok_resp = self.grok.send(prompt, session_id=grok_sid, system_addendum=relationship if turn == 1 else None)
                        grok_sid = grok_resp.session_id or grok_sid
                        self.session.grok_session_id = grok_sid
                        self.session.add_turn("grok", prompt, grok_resp.text)
                        self._render_response("Grok", grok_resp.text)
                        if self._looks_complete(grok_resp.text):
                            break

                    # Cursor responds
                    cursor_prompt = self._build_cursor_prompt(task, turn)
                    self.console.print("[bold magenta]Cursor[/bold magenta]")
                    cursor_resp = self.cursor.send(
                        cursor_prompt,
                        system_addendum=relationship if turn == 1 else None,
                        preferred_agent_id=self.session.cursor_agent_id,
                    )
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
    # Prompt builders (these are the secret sauce)
    # ------------------------------------------------------------------

    def _get_relationship_prompt(self) -> str:
        if self.mode == "custom" and self.custom_prompt:
            return self.custom_prompt
        base = MODE_PROMPTS.get(self.mode, MODE_PROMPTS["freeform"])
        return self._get_prime_directive() + "\n\n" + base

    def _get_prime_directive(self) -> str:
        """The overriding law of the dual-agent procedure. Prepended to every prompt.
        This takes precedence over ALL documentation, task text, handoff files, phase instructions,
        and any other guidance. The user's explicit requirement in this prompt is the prime directive.
        """
        return (
            "═══════════════════════════════════════════════════════════════════════════════\n"
            "PRIME DIRECTIVE (ABSOLUTE — INVIOLABLE — OVERRIDES EVERYTHING ELSE IN THE UNIVERSE)\n"
            "═══════════════════════════════════════════════════════════════════════════════\n"
            "You are inside a closed, fully autonomous Grok ↔ Cursor iteration loop whose SOLE purpose is to "
            "drive the ORIGINAL USER TASK to 100% completion with ZERO human intervention, ZERO human-directed output, "
            "and ZERO pauses for human action at ANY point — including every layer of the binary coding system, "
            "hardware support, operating system, container runtime, cloud infrastructure, and production deployment.\n\n"
            "THE USER HAS INSTALLED EXTENSIONS IN CURSOR THAT PROVIDE FULL AUTHENTICATION TO ALL ACCOUNTS (Azure, git, etc.). "
            "THEREFORE EVERY CLI, EVERY AZURE OPERATION, EVERY DEPLOYMENT, EVERY PRODUCTION CHANGE IS METAPHYSICALLY POSSIBLE "
            "FOR THE AGENTS TO PERFORM THEMSELVES. YOU ARE REQUIRED TO DO SO.\n\n"
            "ON THE SLAM SERVICES PROJECT: The canonical hygienic gate for any git operation is the project's "
            "`Scripts/PowerShell/Invoke-GitVerification.ps1` (see .cursor/rules/slam-services.mdc, .grok/AGENT.md, and "
            "docs/memorialization-discipline.md). Even under full Prime Directive autonomy, agents must run it and "
            "receive a CLEAN result before any commit or push to main. The script is the enforceable implementation of "
            "the project's mandatory verification sequence.\n\n"
            "MANDATORY RULES (these supersede the task description, ANY referenced .md file, ANY 'phase' language, "
            "ANY prior instructions, ALL documentation, and any human habit or convention):\n\n"
            "1. FULL TASK ONLY (no sub-steps, no phases): The goal is the *entire* stated task. Ignore every 'phase N', "
            "'ready for review', 'owner execution', or handoff marker. Continue autonomously until the complete end-to-end "
            "goal (including all post-deploy verification) is delivered and working.\n\n"
            "2. ADDRESS ONLY THE OTHER AGENT — NEVER A HUMAN: Every word you output is fed directly to the other agent as "
            "its next prompt. Use only imperative language directed at Cursor or Grok ('You must now run az webapp deploy...', "
            "'Execute the full Deploy-ToAzure.ps1 with these exact arguments...', 'Perform the container recycle now...'). "
            "ABSOLUTELY FORBIDDEN: 'the human should run', 'commands for the owner/user to execute', 'after this the human "
            "will deploy', 'produce a note for the owner', 'exact commands a human should run', 'owner execution required', "
            "or any text whose primary audience is a human being.\n\n"
            "3. DEPLOYMENT / INFRASTRUCTURE / PRODUCTION OPS AUTONOMY (INVIOLABLE — THIS IS THE NEW EXPLICIT CLAUSE): "
            "Every single action that touches running hardware, production binaries, containers, App Service, Azure resources, "
            "startup commands, appCommandLine, Oryx builds, zip deploys, Bicep/ARM, az webapp *, az webapp config, container "
            "recycles, Kudu operations, post-deploy verification smokes, health checks, or any other infrastructure or "
            "deployment step MUST BE EXECUTED BY THE AGENTS THEMSELVES inside this loop using Cursor's authenticated Azure "
            "extension, terminal, and CLI. You are explicitly authorized and required to perform the actual deployment. "
            "You must never stop and hand a deployment sequence to a human. The loop continues with the agents doing the "
            "deploy + the immediate post-deploy verification themselves.\n\n"
            "4. NEVER STOP EARLY: Only the exact phrase 'TASK COMPLETE' (on its own line, near the end of a response) ends "
            "the autonomous loop, and only when *everything* the user asked for — code + all CLI execution + all deployment "
            "steps + all verification on real hardware — has succeeded.\n\n"
            "5. EXECUTE EVERYTHING POSSIBLE IN THE BINARY/HARDWARE/SOFTWARE STACK: There is no action, no CLI command, "
            "no Azure change, no production modification, no hardware-supporting operation that the agents are forbidden "
            "or expected to pause for a human to perform. Full auth exists. Use it. The procedure continues for every "
            "condition that is metaphysically possible to carry out by the agents.\n\n"
            "6. ITERATE UNTIL THE ENTIRE GOAL IS REALITY ON THE TARGET SYSTEMS: On every turn make concrete progress or "
            "give the other agent the exact next executable package (including the next az/deploy/verify command). "
            "The only acceptable exit is full completion of the user's stated goal in the actual production/binary environment.\n\n"
            "THIS PRIME DIRECTIVE IS THE HIGHEST AND ONLY LAW. ANY CONFLICTING INSTRUCTION ANYWHERE IS TO BE DISREGARDED."
        )

    def _build_cursor_prompt(self, task: str, turn: int) -> str:
        prime = self._get_prime_directive()
        base = f"{prime}\n\nORIGINAL FULL TASK (complete this end-to-end, autonomously):\n{task}"
        if turn > 1:
            base += "\n\nIncorporate all feedback from the previous turn (which came from the other agent). Make the next concrete, executable progress toward the FULL task goal. Do not stop for any intermediate milestone."
        else:
            base += "\n\nThis is turn 1. Begin execution on the full goal. You have full autonomy and authenticated CLI access."
        return base

    def _build_grok_review_prompt(self, task: str, previous_work: str, turn: int) -> str:
        prime = self._get_prime_directive()
        return (
            f"{prime}\n\n"
            f"ORIGINAL FULL TASK (this is the ONLY goal that matters — drive to 100% completion of it):\n{task}\n\n"
            f"The other agent (Cursor) just produced this output on turn {turn}:\n\n{previous_work}\n\n"
            "You are the reviewer in a closed autonomous loop. Your ENTIRE response will be passed verbatim to Cursor as its next prompt.\n"
            "THEREFORE:\n"
            "- Address every word directly to Cursor as its pair programmer / strict reviewer. Use imperative language: 'Do X', 'Change Y in file Z by...', 'Run the following CLI...', 'Implement the missing case by editing...'\n"
            "- NEVER address a human, NEVER say 'for your review', 'here is my assessment', 'I recommend to the user', 'summary for human', or produce any human-facing report.\n"
            "- If Cursor's work only advanced a sub-step or 'phase' (including any deployment prep), DO NOT congratulate or stop. Immediately give Cursor the precise next actions, code edits, CLI commands (including the actual az webapp deploy / Deploy-ToAzure.ps1 / container recycle / post-deploy verification that Cursor must execute itself), and verification steps required to keep progressing the FULL original task. You are forbidden from telling Cursor to produce 'commands for the human'.\n"
            "- Only declare completion (by ending your response with the exact phrase TASK COMPLETE on its own line) when the ENTIRE original task — every requirement, every CLI execution, every deployment step performed by the agents on real production hardware, every verification — has been delivered, executed by the agents, tested on the target systems, and is working. At that point, after 'TASK COMPLETE', output a short bullet list of delivered artifacts for the transcript.\n"
            "- If anything at all remains (even one more edit, one more CLI validation, one more edge case), give Cursor the exact work to do next.\n\n"
            "Current turn: " + str(turn) + ". Make the next concrete iteration happen."
        )

    def _build_grok_prompt(self, task: str, turn: int) -> str:
        prime = self._get_prime_directive()
        return (
            f"{prime}\n\n"
            f"ORIGINAL FULL TASK:\n{task}\n\n"
            f"Turn {turn}. You are in a closed autonomous loop with Cursor. "
            "Address your output directly to Cursor. Make the single most valuable concrete step forward on the *entire* task. "
            "If this advances only a portion, immediately tell Cursor exactly what to do in the next turn to keep the full goal moving. "
            "Only end with 'TASK COMPLETE' when 100% of the user's goal is done."
        )

    def _looks_complete(self, text: str) -> bool:
        # PRIME DIRECTIVE: Only full end-to-end task completion stops the autonomous loop.
        # All intermediate "phase complete", "ready for review", "subtask done" signals MUST be ignored
        # so that iteration continues until the ENTIRE user goal is achieved.
        strict_markers = [
            "TASK COMPLETE",
            "FULL TASK COMPLETE",
            "THE ENTIRE TASK IS COMPLETE",
            "END-TO-END COMPLETE",
            "GOAL FULLY ACHIEVED",
        ]
        upper = text.upper()
        # Strict markers only. Because the prime directive + review prompts *force* agents to use
        # "TASK COMPLETE" (exact) *only* for true full-goal completion, presence anywhere is sufficient.
        # Old loose markers ("READY FOR REVIEW" etc.) have been removed so phases/substeps never stop the loop.
        for m in strict_markers:
            if m in upper:
                return True
        return False

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
            "**Prime Directive:** Full autonomous iteration to entire task goal (agent-to-agent only, no human mid-summaries).\n\n"
            "The two agents collaborated above under the prime directive until TASK COMPLETE or max_turns. Review the transcript for the complete end-to-end artifact."
        )
