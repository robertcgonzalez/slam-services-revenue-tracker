# Dual-Agent — 3-Minute Windows Quickstart

## Option A: Fast local setup (recommended first time)

```powershell
cd C:\slam-services-project\tools\dual-agent

# Preferred (much faster)
.\scripts\setup-uv.ps1

# Fallback if you don't have uv yet
.\scripts\setup.ps1
```

## Option B: Install globally (run `dual-agent` from anywhere)

```powershell
cd C:\slam-services-project\tools\dual-agent
.\scripts\install-global.ps1
```

This installs to `~/.grok/tools/dual-agent` and creates a launcher in `~/.grok/bin`.

**One-time step after global install:**
Add `~\.grok\bin` to your PATH, then you can run `dual-agent` from any folder.

## 2. Add your Cursor API key

Edit the `.env` file (either in the local folder or `~/.grok/tools/dual-agent/.env`) and add:

```env
CURSOR_API_KEY=cur_your_actual_key_here
```

Get the key here: https://cursor.com/dashboard/integrations

## 3. Run it

```powershell
# If using local venv
.\.venv\Scripts\Activate.ps1
dual-agent run "Improve error handling in the payee extractor" --mode reviewer-implementer

# If installed globally (after adding to PATH)
dual-agent run "Improve error handling in the payee extractor" --mode reviewer-implementer
```

## Common Commands

```powershell
dual-agent list                 # See past sessions
dual-agent resume <id>          # Continue an old one
dual-agent modes                # See all collaboration styles
dual-agent doctor               # (Coming soon) Environment check
```

That's it. No more copy-pasting between two AIs.
