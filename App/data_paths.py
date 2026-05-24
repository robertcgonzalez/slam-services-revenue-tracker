"""CSV data path resolution for local dev and Azure App Service."""

from __future__ import annotations

import os
from pathlib import Path

CLIENTS_FILE = "Clients.csv"
REQUESTS_FILE = "RevenueRequests.csv"
MIGRATION_SUBDIR = Path("Data") / "Revenue_Tracker_Migration"


def _has_required_csvs(folder: Path) -> bool:
    return (folder / CLIENTS_FILE).is_file() and (folder / REQUESTS_FILE).is_file()


def _candidate_paths() -> list[Path]:
    app_dir = Path(__file__).resolve().parent
    repo_root = app_dir.parent
    cwd = Path.cwd()

    bases = [
        repo_root,
        cwd,
        Path("/home/site/wwwroot"),
        app_dir,
    ]

    candidates: list[Path] = []

    env_override = os.environ.get("SLAM_DATA_PATH", "").strip()
    if env_override:
        candidates.append(Path(env_override))

    for base in bases:
        candidates.append(base / MIGRATION_SUBDIR)
        # Misplaced flat layout (CSVs directly under Data/)
        candidates.append(base / "Data")

    # Legacy relative paths
    candidates.extend(
        [
            repo_root / MIGRATION_SUBDIR,
            Path("/home/site/wwwroot/Data/Revenue_Tracker_Migration"),
            Path("Data/Revenue_Tracker_Migration"),
            Path("../Data/Revenue_Tracker_Migration"),
        ]
    )

    seen: set[str] = set()
    unique: list[Path] = []
    for raw in candidates:
        try:
            resolved = raw.resolve()
        except OSError:
            resolved = raw
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def resolve_data_path() -> tuple[Path | None, list[str]]:
    """Return (data_folder, diagnostic_log_lines)."""
    logs: list[str] = []
    logs.append(f"Python cwd: {Path.cwd()}")
    logs.append(f"App module dir: {Path(__file__).resolve().parent}")
    if os.environ.get("SLAM_DATA_PATH"):
        logs.append(f"SLAM_DATA_PATH={os.environ['SLAM_DATA_PATH']}")

    for folder in _candidate_paths():
        clients = folder / CLIENTS_FILE
        requests = folder / REQUESTS_FILE
        if _has_required_csvs(folder):
            logs.append(f"MATCH: {folder}")
            return folder, logs
        exists = folder.exists()
        logs.append(
            f"miss: {folder} (dir_exists={exists}, "
            f"clients={clients.is_file()}, requests={requests.is_file()})"
        )

    # List wwwroot for Azure diagnostics when nothing matched
    wwwroot = Path("/home/site/wwwroot")
    if wwwroot.is_dir():
        try:
            top = sorted(p.name for p in wwwroot.iterdir())
            logs.append(f"wwwroot contents: {top[:30]}")
            data_dir = wwwroot / "Data"
            if data_dir.is_dir():
                logs.append(f"Data/ contents: {sorted(p.name for p in data_dir.iterdir())[:20]}")
        except OSError as exc:
            logs.append(f"wwwroot listing failed: {exc}")

    return None, logs


def render_data_path_error(logs: list[str]) -> str:
    """Human-readable error for missing CSV data."""
    lines = [
        "Could not locate Clients.csv and RevenueRequests.csv.",
        "",
        "Expected layout: Data/Revenue_Tracker_Migration/ at deployment root.",
        "Azure: /home/site/wwwroot/Data/Revenue_Tracker_Migration/",
        "",
        "Fix options:",
        "1. Manual deploy — include Data/ in flat zip (see README).",
        "2. Kudu — upload Data/Revenue_Tracker_Migration/ to wwwroot.",
        "3. App Setting — SLAM_DATA_PATH=/home/site/wwwroot/Data/Revenue_Tracker_Migration",
        "4. Phase 3 — set USE_POSTGRES=true after database migration.",
        "",
        "Path diagnostics:",
    ]
    lines.extend(f"  • {line}" for line in logs)
    return "\n".join(lines)
