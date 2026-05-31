#!/usr/bin/env python3
"""Headless Gate A3 smoke on App Service (Kudu / SSH). Upload PDFs to /tmp first."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "App"))

from bank_statements import (  # noqa: E402
    emit_gate_a3_smoke_evidence,
    post_process_bank_statement_df,
    run_azure_ocr_pipeline,
)

_SMOKE_TMP = Path("/home/site/wwwroot/tmp")
SMOKES = [
    ("HCC 2026-04.pdf", "HCC", str(_SMOKE_TMP / "HCC_2026-04.pdf")),
    (
        "Auto_Body_Center_Jan_26_Statement.pdf",
        "Auto Body Center",
        str(_SMOKE_TMP / "Auto_Body_Center_Jan_26_Statement.pdf"),
    ),
]


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("gate_a3_headless_smoke")
    failed = 0
    for pdf_name, client, path_str in SMOKES:
        path = Path(path_str)
        if not path.is_file():
            print(f"SKIP missing file: {path}", file=sys.stderr)
            failed += 1
            continue
        pdf_bytes = path.read_bytes()
        print(f"=== Processing {pdf_name} ({len(pdf_bytes)} bytes) ===", flush=True)
        df, logs, meta = run_azure_ocr_pipeline(
            pdf_bytes, pdf_name, client, logger, timeout_sec=600
        )
        rules_info = (meta or {}).get("payee_rules_info")
        if df is not None and not df.empty and not rules_info:
            df, rules_info = post_process_bank_statement_df(
                df, client, touch_last_used=False
            )
        emit_gate_a3_smoke_evidence(
            pdf_name,
            df,
            meta,
            logs,
            logger,
            client_name=client,
            rules_info=rules_info,
        )
        status = meta.get("status")
        rows = len(df) if df is not None else 0
        crops = meta.get("cropped_check_count", 0)
        print(
            f"DONE {pdf_name} status={status} rows={rows} crops={crops}",
            flush=True,
        )
        if status not in ("success", "partial"):
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
