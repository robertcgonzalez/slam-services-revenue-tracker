"""Command-line interface for dual-agent."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

# Windows console encoding robustness (prevents UnicodeEncodeError with rich on cp1252)
# Especially important for long Cursor responses containing arrows, emojis, etc.
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        import os
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        os.environ.setdefault("PYTHONLEGACYWINDOWSSTDIO", "1")

from .config import DualAgentSettings, CollaborationMode
from .orchestrator import DualAgentOrchestrator
from .session import CollaborationSession

app = typer.Typer(
    name="dual-agent",
    help="Run autonomous collaboration loops between Grok and Cursor agents.",
    rich_markup_mode="markdown",
    no_args_is_help=True,
)
console = Console()


@app.command()
def run(
    task: Annotated[str, typer.Argument(help="The task both agents should collaborate on.")],
    mode: Annotated[
        CollaborationMode,
        typer.Option("--mode", "-m", help="Collaboration personality / division of labor.")
    ] = "reviewer-implementer",
    max_turns: Annotated[
        int | None,
        typer.Option("--max-turns", help="Maximum turns before forced stop. Use 12-30+ for full autonomous end-to-end tasks (prime directive drives natural TASK COMPLETE when whole goal is done).")
    ] = None,
    cursor_model: Annotated[str | None, typer.Option("--cursor-model")] = None,
    grok_model: Annotated[str | None, typer.Option("--grok-model")] = None,
    yolo: Annotated[bool, typer.Option("--yolo", help="Auto-approve everything on both sides (dangerous).")] = False,
    cwd: Annotated[Path | None, typer.Option("--cwd", help="Working directory for both agents.")] = None,
    export: Annotated[Path | None, typer.Option("--export", help="Write full transcript to this file when done.")] = None,
) -> None:
    """Start a new Grok ↔ Cursor collaboration on a task."""
    settings = _load_settings(cursor_model, grok_model, yolo, cwd)

    orchestrator = DualAgentOrchestrator(
        settings=settings,
        mode=mode,
        console=console,
    )

    session = orchestrator.run(task, max_turns=max_turns)

    if export and session:
        export.write_text(_format_transcript(session), encoding="utf-8")
        console.print(f"[green]Transcript exported to[/green] {export}")


@app.command()
def resume(
    session_id: Annotated[str, typer.Argument(help="The session ID to resume (from `dual-agent list`).")],
    max_turns: Annotated[int | None, typer.Option("--max-turns")] = None,
) -> None:
    """Resume a previous collaboration session."""
    settings = _load_settings()

    session = CollaborationSession.load(settings.sessions_dir, session_id)
    console.print(f"[cyan]Resuming task:[/cyan] {session.task}")

    orchestrator = DualAgentOrchestrator(
        settings=settings,
        mode=session.mode,  # type: ignore
        console=console,
    )
    orchestrator.run(session.task, max_turns=max_turns, resume_session_id=session_id)


@app.command("list")
def list_sessions() -> None:
    """List all previous collaboration sessions."""
    settings = _load_settings()
    sessions = CollaborationSession.list_all(settings.sessions_dir)

    if not sessions:
        console.print("[yellow]No sessions found.[/yellow]")
        return

    table = Table(title="Dual-Agent Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Task", style="white")
    table.add_column("Mode", style="magenta")
    table.add_column("Turns", justify="right")
    table.add_column("Status", style="green")
    table.add_column("Updated", style="dim")

    for s in sessions:
        table.add_row(
            s["session_id"],
            s["task"][:60] + ("..." if len(s["task"]) > 60 else ""),
            s["mode"],
            str(s["turns"]),
            s["status"],
            s["updated_at"][:19] if s["updated_at"] else "",
        )

    console.print(table)


@app.command()
def show(session_id: str) -> None:
    """Show the full transcript of a session."""
    settings = _load_settings()
    session = CollaborationSession.load(settings.sessions_dir, session_id)

    console.print(f"[bold]Session:[/bold] {session.session_id}")
    console.print(f"[bold]Task:[/bold] {session.task}")
    console.print(f"[bold]Mode:[/bold] {session.mode}  |  Status: {session.status}\n")

    for t in session.turns:
        speaker = "[green]Grok[/green]" if t.speaker == "grok" else "[magenta]Cursor[/magenta]"
        console.print(f"--- Turn {t.turn_number} — {speaker} ---")
        console.print(t.response[:3000])
        if len(t.response) > 3000:
            console.print("[dim]... (truncated)[/dim]")
        console.print()


@app.command()
def modes() -> None:
    """List available collaboration modes with descriptions."""
    from rich.table import Table
    from .config import MODE_PROMPTS

    table = Table(title="Collaboration Modes", show_lines=True)
    table.add_column("Mode", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")

    descriptions = {
        "freeform": "Free turns, but prime directive applies: address only the other agent; iterate to full task goal only.",
        "reviewer-implementer": "Cursor implements + executes (full CLI/auth). Grok reviews *directly to Cursor*. Autonomous loop to entire task complete (prime directive overrides all phase signals).",
        "researcher-builder": "Grok plans/research. Cursor executes every step (code, CLI, test, deploy). Full autonomous run until whole goal done.",
        "critic-refiner": "Agents relentlessly critique each other (direct address only). No human summaries. Ends only on full TASK COMPLETE.",
        "architect-coder": "Grok high-level design. Cursor implements+executes all the way. Prime directive: full goal, agent-to-agent only.",
        "custom": "Your relationship prompt + mandatory prime directive overlay (full autonomous iteration, no mid-run human summaries).",
    }

    for name in MODE_PROMPTS.keys():
        table.add_row(name, descriptions.get(name, ""))

    console.print(table)


@app.command()
def doctor() -> None:
    """Check that your environment is ready to run dual-agent collaborations."""
    console.print("[bold]dual-agent doctor[/bold]\n")

    settings = _load_settings()
    ok = True

    # Check Cursor key (support both user keys and team/service account keys)
    valid_prefixes = ("cur_", "crsr_")
    if settings.cursor_api_key and settings.cursor_api_key.startswith(valid_prefixes):
        console.print("[green][OK][/green] CURSOR_API_KEY looks valid")
        key_ok = True
    else:
        console.print("[red][FAIL][/red] CURSOR_API_KEY is missing or invalid in .env")
        console.print("[dim]   Get one at: https://cursor.com/dashboard/integrations")
        console.print("[dim]   Then add CURSOR_API_KEY=cur_... (or crsr_...) to .env")
        console.print("[dim]   The tool now checks tools/dual-agent/.env first (most reliable for SLAM work via the Invoke wrapper).[/dim]")
        console.print("[dim]   (Real Cursor agent creation test will be skipped)[/dim]")
        key_ok = False
        ok = False

    # Check grok CLI
    try:
        result = __import__("subprocess").run(
            ["grok", "--help"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            console.print("[green][OK][/green] grok CLI is available")
        else:
            console.print("[red][FAIL][/red] grok CLI returned an error")
            ok = False
    except Exception:
        console.print("[red][FAIL][/red] grok CLI not found in PATH")
        ok = False

    # Check Cursor SDK import
    try:
        import cursor_sdk  # noqa: F401
        console.print("[green][OK][/green] cursor-sdk is importable")
    except ImportError:
        console.print("[red][FAIL][/red] cursor-sdk is not installed in the current environment")
        ok = False

    # Check working directory
    if settings.effective_work_dir.exists():
        console.print(f"[green][OK][/green] Working directory: {settings.effective_work_dir}")
    else:
        console.print("[red][FAIL][/red] Configured working directory does not exist")
        ok = False

    console.print()

    # Real Cursor agent creation test (the actual handoff) — only if we have a key
    if key_ok:
        console.print("[bold]Testing actual Cursor handoff (creating a short-lived agent)...[/bold]")
        try:
            from .cursor_client import CursorClient

            test_client = CursorClient(settings, console=console)
            test_client.ensure_agent()

            if test_client.agent_id:
                console.print(f"[green][OK][/green] Successfully created Cursor agent: [cyan]{test_client.agent_id}[/cyan]")
                test_client.close()
            else:
                console.print("[yellow][WARN][/yellow] Cursor agent was created but no agent_id was returned")
                ok = False
        except Exception as e:
            console.print(f"[red][FAIL][/red] Cursor handoff test failed: {e}")
            console.print("[dim]This is the most common cause of 'handoff feature did not work'.[/dim]")
            ok = False
    else:
        console.print("[dim]Skipping live Cursor agent creation test (no valid CURSOR_API_KEY)[/dim]")

    console.print()
    if ok:
        console.print("[bold green]Environment looks good. Full autonomous Grok ↔ Cursor iteration (prime directive: entire task, no mid-run human summaries) should work at full capacity.[/bold green]")
    else:
        console.print("[bold red]Problems detected. Fix the issues above before running real collaborations.[/bold red]")
        console.print("[bold red]Some checks failed. Fix the issues above before running dual-agent.[/bold red]")

    # Platform guidance for the known Windows + Python 3.14 bridge issues
    import sys
    if sys.version_info >= (3, 12):
        console.print()
        console.print("[yellow]Note: You are running on Python >= 3.12.[/yellow]")
        console.print("[yellow]For SLAM Services work, the strongly recommended path is the project's hardened Python 3.10 venv:[/yellow]")
        console.print("[yellow]  .\\Scripts\\PowerShell\\Invoke-DualAgentHandoff.ps1 -Directive \"docs/handoffs/xxx.md\" -MaxTurns 15[/yellow]")
        console.print("[yellow]  (Prime directive ensures full autonomous run to complete goal; use higher MaxTurns for end-to-end tasks.)[/yellow]")


@app.command("templates")
def list_templates(
    name: Annotated[str | None, typer.Argument(help="Show full content of a specific template")] = None,
) -> None:
    """List or show pre-baked collaboration templates tailored to this codebase."""
    from pathlib import Path

    # Try several possible locations (source layout vs installed global layout)
    candidates = [
        Path(__file__).resolve().parents[2] / "examples" / "templates",  # source dev layout
        Path(__file__).resolve().parent.parent / "examples" / "templates",  # inside package
        Path(__file__).resolve().parents[3] / "examples" / "templates",  # global install root
    ]
    templates_dir = next((c for c in candidates if c.exists()), None)

    if not templates_dir or not templates_dir.exists():
        console.print("[yellow]No templates directory found.[/yellow]")
        return

    template_files = sorted(templates_dir.glob("*.md"))

    if name:
        target = templates_dir / f"{name}.md"
        if not target.exists():
            console.print(f"[red]Template '{name}' not found.[/red]")
            return
        console.print(target.read_text(encoding="utf-8"))
        return

    from rich.table import Table

    console.print("[bold]Available Pre-Baked Templates[/bold] (use `dual-agent templates <name>` to view full text)\n")

    table = Table(title="Dual-Agent Templates for SLAM Services Project")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Category", style="magenta")
    table.add_column("Difficulty", style="yellow")
    table.add_column("Best Mode", style="green")
    table.add_column("Description", style="white")

    for f in template_files:
        content = f.read_text(encoding="utf-8")
        meta = {}
        if content.startswith("---"):
            try:
                import yaml
                header = content.split("---")[1]
                meta = yaml.safe_load(header) or {}
            except Exception:
                pass

        desc = ""
        for line in content.splitlines():
            if line.strip().startswith("# ") and "Task:" in line:
                desc = line.strip("# ").strip()
                break
            if line.strip().startswith("# ") and len(desc) < 10:
                desc = line.strip("# ").strip()

        table.add_row(
            f.stem,
            meta.get("category", "-"),
            meta.get("difficulty", "-"),
            meta.get("recommended_mode", "-"),
            (desc or "No description")[:65] + ("..." if len(desc) > 65 else ""),
        )

    console.print(table)
    console.print("\n[dim]Tip: dual-agent templates payee-extractor-hardening[/dim]")


def _load_settings(
    cursor_model: str | None = None,
    grok_model: str | None = None,
    yolo: bool = False,
    cwd: Path | None = None,
) -> DualAgentSettings:
    """Load settings with optional CLI overrides."""
    s = DualAgentSettings()

    if cursor_model:
        s.cursor_model = cursor_model
    if grok_model:
        s.grok_model = grok_model
    if yolo:
        s.yolo_grok = True
        s.yolo_cursor = True
    if cwd:
        s.work_dir = cwd

    s.ensure_directories()
    return s


def _format_transcript(session: CollaborationSession) -> str:
    lines = [
        f"# Dual-Agent Session {session.session_id}",
        f"**Task:** {session.task}",
        f"**Mode:** {session.mode}",
        f"**Status:** {session.status}",
        "",
        "---",
        "",
    ]
    for t in session.turns:
        lines.append(f"## Turn {t.turn_number} — {t.speaker.upper()}")
        lines.append("")
        lines.append(t.response)
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    app()
