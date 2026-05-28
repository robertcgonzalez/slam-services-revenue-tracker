# Onboarding for Laura: Codespaces in 5 Minutes

This page is for non-technical first-time setup.

## 1) One-time setup

Install these apps:

- GitHub CLI (`gh`)
- Git
- VS Code

Then sign in once:

```bash
gh auth login --scopes codespace
```

## 2) Create or open your Codespace

```bash
gh cs list
gh cs create --repo <owner/repo> --branch main
gh cs ssh <codespace-name>
```

If `gh cs list` already shows one, you can skip `gh cs create`.

## 3) Start the app in Codespaces

Inside the Codespace terminal:

```bash
cd /workspaces/SLAM-Services-Project
source .venv/bin/activate
slam-info
slam-run
```

Open the forwarded Streamlit link and use the password Robert gives you.

## 4) If Robert gave you a `.env` token file

Use this helper once instead of the interactive login:

```bash
bash Scripts/setup-codespace-auth.sh
```

This script reads `SLAM_GH_TOKEN` from your local `.env` only. Never commit `.env`.

## 5) Optional validation command (only when Robert asks)

```bash
.venv/bin/python Scripts/test_local_ocr_regression.py
```
