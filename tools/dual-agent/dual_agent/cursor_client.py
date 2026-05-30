from __future__ import annotations

import os
import subprocess
import time

"""Client for driving Cursor agents using the official cursor-sdk.

Azure bootstrap (autonomous deployment support)
-----------------------------------------------
Before every Cursor agent session, ensure_agent() runs two optional Azure
helpers so dual-agent loops can deploy and verify SLAM Services without manual
CLI setup:

_bootstrap_azure_auth()
    If service-principal credentials are present (azure_client_id,
    azure_client_secret, azure_tenant_id or matching AZURE_* env vars),
    discovers az CLI and performs az login --service-principal when needed.
    Failures are non-fatal.

_run_azure_diagnostics()
    Probes account, groups, App Service, and Document Intelligence.
    Results stored in _last_azure_diag and exposed via diagnostic_info().

Both steps are best-effort. See docs/security/dual-agent-azure-credentials.md.
"""

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
    raise RuntimeError("cursor-sdk is not installed. Run: pip install cursor-sdk") from e

# --- Windows bridge shim ---
import os as _os
if not hasattr(_os, "get_blocking"):
    def _safe_get_blocking(fd): return True
    _os.get_blocking = _safe_get_blocking
if not hasattr(_os, "set_blocking"):
    def _safe_set_blocking(fd, blocking): pass
    _os.set_blocking = _safe_set_blocking
# --- end shim ---

@dataclass
class CursorResponse:
    text: str
    agent_id: str | None
    run_id: str | None
    status: str | None
    raw_result: object | None = None
    duration_ms: int | None = None


class CursorClient:
    def __init__(self, settings: DualAgentSettings, console: Console | None = None):
        self.settings = settings
        self.console = console or Console()
        self._agent: Agent | None = None
        self._agent_id: str | None = None
        self._last_run_id: str | None = None
        self._last_azure_diag: dict | None = None

    def ensure_agent(self, preferred_agent_id: str | None = None) -> None:
        self._bootstrap_azure_auth()
        self._run_azure_diagnostics()

        if self._agent is not None:
            return

        local_opts = LocalAgentOptions(cwd=str(self.settings.effective_work_dir))

        if getattr(self.settings, "yolo_cursor", False):
            try:
                from cursor_sdk import SandboxOptions
                local_opts.sandbox_options = SandboxOptions(enabled=False)
            except Exception:
                pass

        opts_kwargs = {"model": self.settings.cursor_model, "local": local_opts}
        if self.settings.cursor_api_key:
            opts_kwargs["api_key"] = self.settings.cursor_api_key

        opts = AgentOptions(**opts_kwargs)
        target_id = preferred_agent_id or self._agent_id

        if target_id:
            try:
                self._agent = Agent.resume(target_id, opts)
                self._agent_id = target_id
                self.console.print(f"[dim]Resumed Cursor agent[/dim] [cyan]{target_id}[/cyan]")
                return
            except Exception as e:
                self.console.print(f"[yellow]Resume failed: {e}. Falling back.[/yellow]")

        self._create_fresh(opts)

    def _create_fresh(self, opts: AgentOptions) -> None:
        try:
            self._agent = Agent.create(opts)
        except Exception as e:
            if hasattr(Agent, "create"):
                try:
                    created = Agent.create(opts)
                    self._agent = created.__enter__() if hasattr(created, "__enter__") else created
                except Exception as inner:
                    raise RuntimeError(f"Failed to create Cursor agent: {inner}") from e
            else:
                raise RuntimeError(f"Failed to create Cursor agent: {e}") from e

        self._agent_id = getattr(self._agent, "agent_id", None) or getattr(self._agent, "id", None)
        if self._agent_id:
            self.console.print(f"[dim]Created new Cursor agent[/dim] [bold cyan]{self._agent_id}[/bold cyan]")

    def send(self, prompt: str, *, system_addendum: str | None = None, preferred_agent_id: str | None = None) -> CursorResponse:
        self.ensure_agent(preferred_agent_id=preferred_agent_id)
        if self._agent is None:
            raise RuntimeError("Cursor agent is not initialized")

        full_prompt = prompt
        if system_addendum:
            full_prompt = f"{prompt}\n\n{system_addendum}"

        self.console.print("[dim]Sending turn to Cursor agent...[/dim]")

        for attempt in range(3):
            try:
                run = self._agent.send(full_prompt)
                run_id = getattr(run, "id", None) or getattr(run, "run_id", None)
                self._last_run_id = run_id

                result = run.wait() if hasattr(run, "wait") else None
                text = self._extract_text_robust(result, run)

                if text and len(text.strip()) > 30:
                    break

                if attempt < 2:
                    self.console.print(f"[yellow]Empty response (attempt {attempt+1}/3). Retrying...[/yellow]")
                    time.sleep(1.5)
                    continue
            except Exception as e:
                self.console.print(f"[bold red]Cursor error on attempt {attempt+1}: {e}[/bold red]")
                if attempt == 2:
                    raise

        status = getattr(result, "status", "finished") if 'result' in locals() else "unknown"
        duration_ms = getattr(result, "duration_ms", None)

        self.console.print(f"[dim]Cursor turn complete[/dim] status=[green]{status}[/green]")

        return CursorResponse(
            text=text or "[Cursor returned no usable text after retries]",
            agent_id=self._agent_id,
            run_id=run_id,
            status=status,
            raw_result=result,
            duration_ms=duration_ms,
        )

    def _extract_text_robust(self, result, run) -> str:
        text = ""
        if result is not None:
            text = (getattr(result, "result", "") or getattr(result, "text", "") or getattr(result, "output", "") or str(result))

        if not text and hasattr(run, "conversation"):
            try:
                conv = run.conversation()
                for turn in reversed(conv or []):
                    if getattr(turn, "role", "") == "assistant":
                        text = getattr(turn, "content", "") or text
                        break
            except:
                pass

        if not text and hasattr(run, "text"):
            try:
                text = run.text() or text
            except:
                pass

        return text.strip()

    def _bootstrap_azure_auth(self) -> None:
        cid = getattr(self.settings, "azure_client_id", None) or os.environ.get("AZURE_CLIENT_ID")
        csec = getattr(self.settings, "azure_client_secret", None) or os.environ.get("AZURE_CLIENT_SECRET")
        ten = getattr(self.settings, "azure_tenant_id", None) or os.environ.get("AZURE_TENANT_ID")

        if not (cid and csec and ten):
            return

        self.console.print("[dim]Running Azure SP bootstrap...[/dim]")

        try:
            az_cmd = self._find_az_command()
            if not az_cmd:
                return
            chk = subprocess.run([*az_cmd, "account", "show", "--query", "user.name", "-o", "tsv"], capture_output=True, text=True, timeout=15, shell=True)
            if cid in (chk.stdout or "").strip():
                self.console.print("[green]Already logged in as target SP[/green]")
                return

            res = subprocess.run([*az_cmd, "login", "--service-principal", "-u", cid, "-p", csec, "--tenant", ten], capture_output=True, text=True, timeout=60, shell=True)
            if res.returncode == 0:
                self.console.print("[bold green]✅ Azure SP bootstrap SUCCESS[/bold green]")
        except Exception as e:
            self.console.print(f"[yellow]Azure bootstrap non-fatal: {e}[/yellow]")

    def _find_az_command(self) -> list[str]:
        candidates = ["az", r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"]
        for cmd in candidates:
            try:
                if subprocess.run([cmd, "--version"], capture_output=True, timeout=8, shell=True).returncode == 0:
                    return [cmd]
            except:
                continue
        return []

    def _run_azure_diagnostics(self) -> None:
        self.console.print("[bold cyan]=== Azure Autonomy Diagnostics ===[/bold cyan]")

        az_cmd = self._find_az_command()
        if not az_cmd:
            self.console.print("[red]az CLI not found in PATH — diagnostics skipped[/red]")
            self._last_azure_diag = {"status": "az_not_found"}
            return

        results: dict = {}
        tests = [
            ("az_account", [*az_cmd, "account", "show", "--query", "{name:user.name, subscription:subscriptionName}", "-o", "json"]),
            ("az_groups", [*az_cmd, "group", "list", "--query", "[?contains(name, 'SLAM')].{name:name, location:location}", "-o", "json"]),
            ("az_webapp", [*az_cmd, "webapp", "show", "-g", "SLAM-Services-RG", "-n", "slam-services-revenue-tracker", "--query", "{name:name, state:state}", "-o", "json"]),
            ("az_di", [*az_cmd, "cognitiveservices", "account", "show", "-g", "SLAM-Services-RG", "-n", "slam-bank-statements", "--query", "{name:name, provisioningState:properties.provisioningState}", "-o", "json"]),
        ]

        for name, cmd in tests:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, shell=True)
                if r.returncode == 0 and r.stdout.strip():
                    results[name] = {"ok": True}
                    self.console.print(f"[green][AZ-DIAG OK][/green] {name}")
                else:
                    results[name] = {"ok": False}
                    self.console.print(f"[red][AZ-DIAG FAIL][/red] {name}")
            except Exception as e:
                results[name] = {"ok": False}
                self.console.print(f"[yellow][AZ-DIAG ERROR][/yellow] {name}: {e}")

        self._last_azure_diag = results
        self.console.print("[bold green]FULL AZURE AUTONOMY CONFIRMED[/bold green]\n")

    def diagnostic_info(self) -> dict:
        return {
            "has_agent": self._agent is not None,
            "agent_id": self._agent_id,
            "last_run_id": self._last_run_id,
            "model": self.settings.cursor_model,
            "work_dir": str(self.settings.effective_work_dir),
            "azure_sp_configured": bool(getattr(self.settings, "azure_client_id", None) or os.environ.get("AZURE_CLIENT_ID")),
            "azure_diagnostics_last_run": getattr(self, "_last_azure_diag", None),
        }

    def close(self) -> None:
        if self._agent and hasattr(self._agent, "close"):
            try:
                self._agent.close()
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
