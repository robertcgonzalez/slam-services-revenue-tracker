# Connecting Cursor (or any agent) to GitHub Codespaces

**Environment policy (authoritative)**:

- GitHub Codespaces is the only supported heavy-OCR environment.
- Local Docker is retired for heavy OCR validation and should not be used as an active path.

**Critical rule**: heavy-OCR commands must run in Codespaces with the provisioned project `.venv`.

---

## First-time auth and onboarding

For non-technical users, start with:

- `Scripts/Onboarding-for-Laura-Codespaces.md`

Technical one-time auth:

```bash
gh auth login --scopes codespace
```

Optional local token helper (`.env` is local only, never committed):

```bash
bash Scripts/setup-codespace-auth.sh
```

---

## Day-to-day connection flow

```bash
gh cs list
gh cs ssh <codespace-name>
```

Inside the Codespace:

```bash
cd /workspaces/SLAM-Services-Project
source .venv/bin/activate
slam-info
slam-run
```

If the Codespace is stopped:

```bash
gh cs start <codespace-name>
```

---

## File sync shortcuts

Push local edits to Codespace:

```bash
gh codespace cp -e -r "App/local_enhanced_ocr.py" "remote:/workspaces/SLAM-Services-Project/App/local_enhanced_ocr.py"
```

Pull artifacts back:

```bash
gh codespace cp -e -r "remote:/workspaces/SLAM-Services-Project/Data/Auto_Body_Center_Jan_26_Statement_LocalOCR.csv" "Data/"
```

---

## Heavy-OCR command pattern

```bash
gh cs ssh <codespace-name> -- "cd /workspaces/SLAM-Services-Project && .venv/bin/python Scripts/test_local_ocr_regression.py"
```

Always run heavy validation in Codespaces and record evidence from that environment.
