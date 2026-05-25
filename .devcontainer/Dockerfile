# SLAM Services — Codespaces Dockerfile (v2.44.2)
#
# Custom image layered on top of the Microsoft Python 3.10 dev container to:
#   1) Remove the third-party Yarn apt source that has a stale GPG key
#      (NO_PUBKEY 62D54FD4003F6525) and breaks any subsequent `apt-get
#      update` — observed during v2.44.1 sshd-feature install attempts.
#   2) Install openssh-server so `gh codespace ssh` and `gh codespace cp`
#      work from a developer's local terminal (the v2.44 verification
#      flow needs `scp` to copy `Data/Auto_Body_Center_Jan_26_Statement.pdf`
#      into the Codespace — that PDF is gitignored and lives only on the
#      developer's local machine).
#   3) Pre-stage the heavy Local Enhanced OCR system libs (poppler-utils,
#      libgl1, libglib2.0-0) at image-build time so `postCreateCommand.sh`
#      runs faster on every fresh Codespace.
#
# Base image is pinned by major tag for reproducibility; matches Azure F1
# App Service runtime (Python 3.10 on Debian Bookworm) for dev parity.

FROM mcr.microsoft.com/devcontainers/python:1-3.10-bookworm

# Drop broken Yarn apt source (idempotent — file may not exist on future
# base image refreshes).
RUN rm -f /etc/apt/sources.list.d/yarn.list \
 && rm -f /usr/share/keyrings/yarn-archive-keyring.gpg \
 && true

# System packages required by the Local Enhanced OCR pipeline + openssh-server
# for gh codespace ssh/cp from a developer's local terminal.
RUN apt-get update -y -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      openssh-server \
      poppler-utils \
      libgl1 \
      libglib2.0-0 \
      ca-certificates \
      curl \
      jq \
 && apt-get autoremove -y -qq \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Configure sshd on port 2222 (matches devcontainers/features/sshd convention
# so `gh codespace ssh` integrates with the GitHub Codespaces agent tunnel).
RUN mkdir -p /var/run/sshd \
 && sed -i 's/^#\?Port .*/Port 2222/' /etc/ssh/sshd_config \
 && sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config \
 && sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config

# Auto-start sshd on interactive shell login (mimics the sshd feature so the
# Codespaces agent can connect without manual `sudo service ssh start`).
RUN printf '\n# >>> SLAM Services Codespaces sshd autostart (v2.44.2) >>>\nif ! pgrep -x sshd > /dev/null 2>&1; then sudo service ssh start > /dev/null 2>&1 || true; fi\n# <<< SLAM Services Codespaces sshd autostart (v2.44.2) <<<\n' >> /home/vscode/.bashrc

# Default to vscode user — postCreateCommand.sh runs as this user, sudo is
# pre-configured by the Microsoft base image.
USER vscode
