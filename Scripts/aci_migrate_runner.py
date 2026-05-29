#!/usr/bin/env python3
"""One-shot Azure Container Instance entrypoint for Postgres CSV migration."""
from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

from azure.storage.blob import BlobServiceClient


def main() -> int:
    acc = os.environ["STORAGE_ACCOUNT"]
    key = os.environ["STORAGE_KEY"]
    container = os.environ["BLOB_CONTAINER"]
    prefix = os.environ["BLOB_PREFIX"]
    svc = BlobServiceClient(
        account_url=f"https://{acc}.blob.core.windows.net",
        credential=key,
    )

    def download(name: str, dest: Path) -> None:
        blob = svc.get_blob_client(container, f"{prefix}/{name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob.download_blob().readall())

    root = Path("/work")
    download("bundle.zip", root / "bundle.zip")
    with zipfile.ZipFile(root / "bundle.zip") as zf:
        zf.extractall(root)
    download("Clients.csv", root / "data" / "Clients.csv")
    download("RevenueRequests.csv", root / "data" / "RevenueRequests.csv")

    os.chdir(root)
    os.environ["POSTGRES_HOST"] = os.environ["PG_HOST"]
    os.environ["POSTGRES_USER"] = os.environ["PG_USER"]
    os.environ["POSTGRES_PASSWORD"] = os.environ["PG_PASSWORD"]
    os.environ["POSTGRES_DB"] = os.environ["PG_DB"]
    os.environ["POSTGRES_SSLMODE"] = "require"
    os.environ["USE_POSTGRES"] = "true"

    for cmd in (
        [sys.executable, "Scripts/init_db.py"],
        [sys.executable, "Scripts/migrate_to_postgres.py", "--dry-run", "--data-path", "data"],
        [sys.executable, "Scripts/migrate_to_postgres.py", "--data-path", "data"],
    ):
        subprocess.check_call(cmd)
    print("MIGRATION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
