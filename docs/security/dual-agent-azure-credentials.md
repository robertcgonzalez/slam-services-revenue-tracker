# Azure Credentials for Dual-Agent Autonomy (SLAM Services)

**Purpose**: Enable the Grok ↔ Cursor dual-agent system to perform authenticated Azure operations autonomously without relying on the user's local Cursor Desktop IDE extensions or interactive logins.

**Date Established**: 2026-05-30
**Owner**: Project infrastructure + dual-agent setup

---

## Why This Is Required

The `cursor-sdk` agents used by the dual-agent orchestrator (in `tools/dual-agent/`) run in isolated execution contexts. They **do not** inherit:

- Extensions authorized inside the Cursor GUI/IDE
- Local `az login` sessions
- Browser-based or extension-managed Azure credentials

This limitation was the root cause of repeated authentication friction during deployment resolution work (Postgres connectivity, App Service config changes, etc.).

To satisfy the project's **Prime Directive** (agents must execute every possible Azure/CLI/deployment step themselves), we use a dedicated Service Principal.

---

## 1. Cursor API Key (for the SDK)

This key allows the Python orchestrator to create and drive Cursor agents.

- Obtain from: https://cursor.com/dashboard/integrations
- Store in (priority order):

  1. `C:\slam-services-project\tools\dual-agent\.env`
  2. `C:\Users\arese\.grok\tools\dual-agent\.env`

```env
CURSOR_API_KEY=cur_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 2. Azure Service Principal

### Creation (Recommended Method)

Run these commands in any authenticated Azure CLI session (PowerShell recommended):

```powershell
$AppName        = "dual-agent-slam-services"
$ResourceGroup  = "SLAM-Services-RG"
$SubscriptionId = (az account show --query id -o tsv)

$sp = az ad sp create-for-rbac `
    --name $AppName `
    --role "Contributor" `
    --scopes "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup" `
    --years 3 `
    --query "{appId:appId, password:password, tenant:tenant}" -o json | ConvertFrom-Json

Write-Host "AZURE_CLIENT_ID     = $($sp.appId)"
Write-Host "AZURE_CLIENT_SECRET = $($sp.password)" -ForegroundColor Yellow
Write-Host "AZURE_TENANT_ID     = $($sp.tenant)"
```

**Copy the secret immediately** — it is only shown once.

### Recommended RBAC (Least Privilege)

After creation, tighten permissions:

```powershell
az role assignment create `
    --assignee $sp.appId `
    --role "Website Contributor" `
    --scope "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup"

az role assignment create `
    --assignee $sp.appId `
    --role "Reader" `
    --scope "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.DBforPostgreSQL/flexibleServers/slam-services-db"
```

Add additional roles as needed (Key Vault, etc.).

---

## 3. Secure Storage

Add to **both** `.env` files:

```env
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_SECRET=your-secret-here
AZURE_TENANT_ID=7194e5a3-c940-4eb9-b91b-35df80e818c3
```

The dual-agent configuration system (`DualAgentSettings`) automatically loads these files. Extra variables are passed through to the environment visible to Cursor agents.

---

## 4. Injection into Dual-Agent Launches

The project wrapper (`Scripts/PowerShell/Invoke-DualAgentHandoff.ps1`) includes logic to forward Azure credentials into the orchestrator process:

```powershell
# Credential injection block (already present)
$azureVars = @('AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET', 'AZURE_TENANT_ID')
foreach ($var in $azureVars) {
    if ($env:$var) {
        [System.Environment]::SetEnvironmentVariable($var, (Get-Item "env:$var").Value, 'Process')
    }
}
```

This ensures Cursor agents launched via the wrapper can authenticate using the service principal.

---

## 5. How Agents Use the Credentials

Inside dual-agent tasks, Cursor can authenticate with:

```powershell
az login --service-principal `
  -u $env:AZURE_CLIENT_ID `
  -p $env:AZURE_CLIENT_SECRET `
  --tenant $env:AZURE_TENANT_ID

az account set --subscription "<your-subscription>"
```

Python code running inside the agent can use `DefaultAzureCredential` or explicit `ClientSecretCredential`.

---

## 6. Testing

Verify with a focused dual-agent run:

```powershell
.\Scripts\PowerShell\Invoke-DualAgentHandoff.ps1 `
  -Task "Authenticate to Azure using only the injected service principal (no local user credentials). List webapps in SLAM-Services-RG and show the current appCommandLine for slam-services-revenue-tracker. Confirm you are running as the dual-agent-slam-services principal." `
  -MaxTurns 4
```

---

## 7. Rotation & Security

- Rotate the client secret every 12–18 months.
- Update both `.env` files when rotating.
- Prefer Azure Key Vault + Managed Identity for production-grade secret handling in the future.
- Never commit `.env` files or secrets to source control.

---

## 8. Related Files

- `tools/dual-agent/dual_agent/config.py` – Environment loading logic
- `Scripts/PowerShell/Invoke-DualAgentHandoff.ps1` – Launch wrapper with injection
- `docs/deployment.md` – Main deployment guide (reference this document)
- `tools/dual-agent/README.md` – Dual-agent documentation

---

**Last Updated**: 2026-05-30  
**Maintained By**: Project infrastructure team + dual-agent automation

This setup enables the Prime Directive: agents perform every executable Azure/CLI/deployment/verification step themselves.