# dual-agent

**Autonomous bidirectional feedback loop between Grok and Cursor agents.**

This tool lets Grok (via headless CLI) and a Cursor agent (via the official Cursor SDK) collaborate on tasks **without you manually pasting output** between them.

It is designed for deep, multi-turn work where the strengths of both models complement each other (e.g. one is better at research/architecture, the other at precise implementation + tool use inside an IDE context).

## Why This Exists

Manual copy-paste between two powerful agents is slow, lossy, and breaks flow. This tool gives you a real orchestrator that:

- Runs both agents programmatically
- Maintains separate conversation state for each
- Supports rich collaboration modes (implementer + reviewer, researcher + coder, critic + refiner, etc.)
- Can run until a stopping condition or for N turns
- Persists sessions so you can resume days later

## Installation (Windows + PowerShell)

### Recommended: Install Globally (run `dual-agent` from any folder)

```powershell
cd C:\slam-services-project\tools\dual-agent
.\scripts\install-global.ps1
```

This installs the tool to `~/.grok/tools/dual-agent` and creates a launcher in `~/.grok/bin`.

**One-time PATH step** (after global install):
Add `~\.grok\bin` to your system PATH. After that you can run `dual-agent` from anywhere.

### Alternative: Local development setup

**Fast path (with uv — strongly recommended on Windows):**

```powershell
.\scripts\setup-uv.ps1
```

**Standard path:**

```powershell
.\scripts\setup.ps1
```

### Get your Cursor API key

1. Go to https://cursor.com/dashboard/integrations
2. Create a new User API Key
3. Paste it into the `.env` file as `CURSOR_API_KEY=cur_...`

### Quick test

```powershell
dual-agent --help
dual-agent modes
```

## Collaboration Modes

| Mode                  | Description                                      | Best For                              |
|-----------------------|--------------------------------------------------|---------------------------------------|
| `freeform`            | Both agents speak freely in turn                 | Open-ended exploration                |
| `reviewer-implementer`| Cursor implements, Grok reviews & critiques      | High-quality production code          |
| `researcher-builder`  | Grok researches + plans, Cursor executes         | Spikes, new features, unknown domains |
| `critic-refiner`      | One agent proposes, the other relentlessly refines | Architecture, design docs, complex logic |
| `architect-coder`     | Grok does high-level design, Cursor writes code  | Large refactors                       |

You can also pass `--mode custom` and provide a system prompt that defines the relationship.

## How It Actually Works

```
┌─────────────────────────────┐
│      dual-agent (orchestrator)
│
│  1. Loads your task + mode
│  2. Creates/resumes two separate agents:
│       - Grok (via `grok -p --output-format json`)
│       - Cursor (via official cursor-sdk)
│  3. Alternates turns with full context handoff
│  4. Streams both sides live
│  5. Stops on "done", max turns, or manual cancel
└─────────────────────────────┘
```

Both agents run against the **same working directory** you launched from (or `--cwd`).

## Session Management

Every run gets a session ID. You can:

```powershell
dual-agent list                  # Show all sessions
dual-agent resume abc123def      # Continue an old collaboration
dual-agent show abc123def        # Inspect the full transcript
```

Sessions are stored in `.dual-agent-sessions/` by default (configurable).

## Global vs Local Installation

- **Global install** (`~/.grok/tools/dual-agent`) is best for daily use across all your projects.
- **Local install** (inside a specific repo) is useful when you want to hack on the tool itself or pin a specific version per project.

You can have both at the same time. The global version is what most people should use.

## Advanced Usage

```powershell
# Use a different model on the Cursor side
dual-agent run "..." --cursor-model claude-3.5-sonnet-20241022

# Use a different Grok model
dual-agent run "..." --grok-model grok-4

# Run completely unattended (both sides in yolo mode)
dual-agent run "..." --yolo

# Custom working directory
dual-agent run "..." --cwd C:\path\to\other\repo

# Export the full conversation when finished
dual-agent run "..." --export transcript.md
```

## Safety Notes

- `--yolo` will let **both** agents execute commands and edit files without asking you. Only use in trusted repos.
- The tool respects your existing `.cursor/rules` and Grok project rules when the agents run.
- Cursor SDK runs inherit the permissions of the API key you provide.

## Development

```powershell
# After cloning / changing code
pip install -e ".[dev]"

ruff check .
ruff format .
```

## Roadmap / Ideas

- [ ] Native support for Cursor "Composer" style long-running agents
- [ ] Web UI / TUI for watching the loop live
- [ ] MCP server so either agent can call the orchestrator as a tool
- [ ] Pre-built high-value prompts for common workflows (migration, security audit, performance pass, etc.)

## Documentation & Status

- **PROJECT_STATUS.md** — Full history of what was built, current capabilities, detailed roadmap, and recommendations
- **QUICKSTART.md** — Fastest way to get running on Windows
- This README — Core usage and installation reference

## License

MIT — use it, modify it, ship it.

---

Built because manual copy-paste between two 10x agents feels like 1997.
