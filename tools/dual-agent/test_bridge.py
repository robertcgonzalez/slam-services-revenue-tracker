"""Minimal test to isolate the Cursor SDK bridge launch failure."""
import sys
from pathlib import Path

# Ensure we can import from the package
sys.path.insert(0, str(Path(__file__).parent))

from dual_agent.config import DualAgentSettings
from dual_agent.cursor_client import CursorClient
from rich.console import Console

console = Console()

print("=== Cursor SDK Bridge Launch Diagnostic ===")
print(f"Python: {sys.version}")
print(f"CWD: {Path.cwd()}")

settings = DualAgentSettings()
print(f"Key loaded (prefix): {settings.cursor_api_key[:8] if settings.cursor_api_key else 'None'}...")
print(f"Model: {settings.cursor_model}")

client = CursorClient(settings, console)

try:
    print("\nAttempting to create fresh Cursor agent (this is where the bridge usually fails)...")
    client.ensure_agent()
    print("[SUCCESS] Agent created:", client.agent_id)
except Exception as e:
    print(f"\n[FAILED] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
finally:
    client.close()
