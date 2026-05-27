# Connecting Cursor (or any agent) to the SLAM Codespace for heavy OCR work

**Primary Codespace name**: `slam-v2-44-codespaces-migration` (the long ID is `slam-v2-44-codespaces-migration-4jrx6vp47x7xfq6wx`)

**Critical rule** (from .cursor/rules/slam-services.mdc and all prior transcripts):
All `slam-info`, `python Scripts/test_local_ocr_regression.py`, `python Scripts/e2e_local_ocr.py`, full pipeline runs against Data/Auto_Body_Center_Jan_26_Statement.pdf, and any EasyOCR / cropper work **MUST** happen inside this Codespace. Never on the Windows laptop.

## Why Cursor sometimes claims "I cannot connect"

- Cursor's agent runs in an isolated terminal context that may not inherit your interactive `gh` authentication (Windows Credential Manager / keyring) or PATH.
- The Codespace must be in "Available" state (not Stopped/Shutdown).
- On Windows, the OpenSSH client that works is the one from Git for Windows (`C:\Program Files\Git\usr\bin\ssh.exe`).
- `gh` CLI must be in the PATH visible to Cursor's agent.

Yesterday (big OCR session) it worked because the context happened to see a fresh `gh` auth and you guided it.

## Verified working connection methods (as of 2026-05-26)

### Method 1 — Recommended: gh cs ssh (easiest, handles start + tunnel)

From a PowerShell that has `gh` on PATH and you are logged in (`gh auth login` if needed):

```powershell
# List to get the exact current name
gh cs list

# Connect (replace with the exact name shown)
gh cs ssh slam-v2-44-codespaces-migration-4jrx6vp47x7xfq6wx

# Or the short display name if it works
gh cs ssh slam-v2-44-codespaces-migration
```

Once inside the Linux shell in the Codespace:

```bash
# Always start here
cd /workspaces/slam-services-revenue-tracker

# Use the full Python from the provisioned venv (do not rely on "python" alias if it points elsewhere)
source .venv/bin/activate
# or direct
/workspaces/slam-services-revenue-tracker/.venv/bin/python -c "import App.local_enhanced_ocr as o; print(o.LOCAL_ENHANCED_OCR_VERSION)"

# The slam-info alias (added by postCreateCommand.sh)
alias slam-info 2>/dev/null || true
python -c "
import App.local_enhanced_ocr as o
import json
caps = o.detect_capabilities()
print(json.dumps({'version': o.LOCAL_ENHANCED_OCR_VERSION, 'capabilities': caps, 'dpi_text': o.OCR_DPI_TEXT, 'dpi_crop': o.OCR_DPI_CROP}, indent=2))
"
```

### Method 2 — File sync without full interactive ssh (gh codespace cp)

This is what the big OCR transcript used successfully for pushing code and pulling results:

```powershell
# From the Windows laptop repo root
# Push local changes to Codespace (example)
gh codespace cp -e -r "App/local_enhanced_ocr.py" "remote:/workspaces/slam-services-revenue-tracker/App/local_enhanced_ocr.py"

# Pull results back
gh codespace cp -e -r "remote:/workspaces/slam-services-revenue-tracker/Data/Auto_Body_Center_Jan_26_Statement_LocalOCR.csv" "Data/"
```

The `-e` flag expands the Codespace name; `-r` is recursive for directories.

### Method 3 — Make plain ssh work (persistent config)

Create or edit `%USERPROFILE%\.ssh\config` (on Windows):

```
Host slam-codespace
    HostName <the-codespace-fqdn-or-use-gh-cs-ssh-proxy>
    User vscode
    IdentityFile ~/.ssh/id_ed25519   # or whatever key gh uses
    StrictHostKeyChecking no
```

Then Cursor (or you) can just `ssh slam-codespace`.

`gh cs ssh` is usually simpler and doesn't require maintaining keys.

## How Cursor should behave (standing instruction for all future sessions)

1. At the very start of any heavy-OCR-related task, run:
   - `gh auth status`
   - `gh cs list`
   - Confirm the target Codespace is "Available". If Stopped, use `gh cs start <name>` first.

2. Prefer `gh codespace cp` for moving files (code, caches, output CSVs) in both directions.

3. Use `gh cs ssh <exact-name>` when you need an interactive or long-running shell to execute `slam-info`, the regression test, e2e_local_ocr.py, ruff, etc.

4. Inside the ssh session, **always** cd to the repo root and use the explicit `.venv/bin/python` path or `source .venv/bin/activate`.

5. Never say "I cannot connect — please run manually and paste the output" if `gh cs list` succeeds in your terminal. Attempt the connection first and report the actual error if it fails.

6. After any remote execution, use `gh codespace cp` to pull the important artifacts (new caches, new LocalOCR_*.csv, logs) back to the laptop so they are visible in the working tree.

## One-time setup on the Windows laptop (if gh cs ssh complains about ssh)

- Ensure Git for Windows is installed (provides ssh.exe).
- Add `C:\Program Files\Git\usr\bin` to PATH (or let Cursor's terminal inherit it).
- Run `gh auth login --scopes codespace` at least once in an interactive PowerShell.

## Quick test from any shell (including Cursor's)

```powershell
gh cs list
gh cs ssh slam-v2-44-codespaces-migration-4jrx6vp47x7xfq6wx -- "cd /workspaces/slam-services-revenue-tracker && .venv/bin/python -c 'import App.local_enhanced_ocr as o; print(o.LOCAL_ENHANCED_OCR_VERSION)'"
```

This non-interactive form is useful for one-off commands.

---

**Last verified working**: 2026-05-26 on the laptop with gh 2.92.0 + Git OpenSSH + the specific Codespace in "Available" state.

Update this file whenever the connection recipe changes.
