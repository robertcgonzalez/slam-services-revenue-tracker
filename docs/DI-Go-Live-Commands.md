# Azure DI Bank Statement Go-Live — Exact Commands (2026)

**Owner decisions baked in**:
- Upgrade `slam-bank-statements` to S0 before Laura pilot.
- Pilot on existing F1 App Service tier; evaluate B1 later.
- Start check leg on `prebuilt-check.us`.
- Full team enablement (no client scoping).
- Schema captured in `db/schema.sql` + `docs/data-model.md`.

**Prerequisites (run once)**:
```powershell
az login
az account set --subscription "<your-subscription-id-or-name>"
```

---

## Step 1 — Upgrade DI Resource to S0 (Production Tier)

```powershell
# From any PowerShell session with az
$RG = "SLAM-Services-RG"
$DI  = "slam-bank-statements"

az cognitiveservices account update `
  --name $DI `
  --resource-group $RG `
  --sku S0

# Verify
az cognitiveservices account show `
  --name $DI `
  --resource-group $RG `
  --query "{name:name, sku:sku.name, endpoint:properties.endpoint}" `
  -o table
```

**Expected**: SKU now shows `S0`. Note the new pricing tier (still very low at SLAM volume).

**Rollback** (rarely needed): Change back to `F0` in the Portal or via the same command with `--sku F0`.

---

## Step 2 — Apply Production DI App Settings (One Command)

```powershell
cd C:\slam-services-project

# Dry run first (highly recommended)
.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1 -WhatIf

# Real run (owner confirmation required inside the script flow)
.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1
```

The script will print the exact settings applied and the rollback command.

**Verify the settings landed**:
```powershell
az webapp config appsettings list `
  -g SLAM-Services-RG `
  -n slam-services-revenue-tracker `
  --query "[?starts_with(name, 'AZURE_DI') || starts_with(name, 'SLAM_IMAGING')].{name:name, value:value}" `
  -o table
```

---

## Step 3 — Redeploy Code

Use the normal production path (either is fine):

**Option A (recommended — polling safe)**:
```powershell
.\Scripts\PowerShell\Build-AzureDeployZip.ps1
.\Scripts\PowerShell\Deploy-ToAzure.ps1
```

**Option B (GitHub Actions)**:
- Push to `main` (or trigger the workflow manually).
- The existing workflow already includes the `azure-ai-documentintelligence` package.

---

## Step 4 — Post-Deploy Health & DI Validation

```powershell
# Full health (now includes DI + schema probes after the health script updates)
.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure

# Or the pure Python version
python Scripts/health_check.py --full
```

**Manual Robert smoke (on the live URL after login)**:
1. Go to Bank Statements.
2. Upload a known-good scanned PDF (e.g. `Data/Auto_Body_Center_Jan_26_Statement.pdf`).
3. Click **Process Statement**.
4. Confirm:
   - Azure DI banner / status appears (not "not configured").
   - Reasonable transaction count + totals.
   - Reconciliation banner is green.
   - Crops appear for imaging pages (if any).
   - "Mark as Received" writes `bank_statement_received=true` successfully (visible in Revenue Requests or via DB query).

---

## Step 5 — Immediate Rollback (if anything feels off)

```powershell
# Removes the DI settings — Bank Statements instantly reverts to previous behavior
.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1 -DisableDI

# Redeploy once more so the sidebar reflects the change cleanly (optional but recommended)
.\Scripts\PowerShell\Deploy-ToAzure.ps1
```

No data is lost. The Grok Vision paste path and lightweight parser continue to work.

---

## Step 6 — Laura + Full Team Pilot Session (Gate)

- Schedule a 45–60 min session.
- Walk through one clean PDF and one hard scanned PDF side-by-side (old Grok paste vs new DI path).
- Confirm payee quality improvement and time saved.
- Explicit owner question: "Ready for daily driver use across the whole team?"

If yes → leave the settings in place. Monitor DI cost for 7–14 days.

---

## Bonus — Schema Validation (Part of Go-Live Confidence)

```powershell
# Quick local check that the canonical schema can be applied
# (requires a local Postgres with $DATABASE_URL or the POSTGRES_* vars)
python -c "
from App.db_utils import init_schema, get_db_engine
eng = get_db_engine()
init_schema(eng)
print('Schema init OK')
"

# Or against the live Azure instance (USE_POSTGRES=true in your local .env for the session)
python Scripts/health_check.py --full
```

The output + the new "Current Implemented" section in `docs/data-model.md` + `db/schema.sql` together prove the production data layer is understood and documented.

---

**End of exact command package**

Keep this file next to `docs/deployment.md`. After the rename (if executed), update the `WebAppName` default in the setter script and any hard-coded references in this file.
