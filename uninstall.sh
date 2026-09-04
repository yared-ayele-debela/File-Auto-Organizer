#!/usr/bin/env bash
# ==============================================================================
# File Auto-Organizer Uninstaller for Ubuntu Linux
# ==============================================================================
set -euo pipefail

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

echo -e "${BOLD}=== Uninstalling File Auto-Organizer ===${RESET}\n"

PURGE=false
for arg in "$@"; do
    if [ "$arg" == "--purge" ]; then
        PURGE=true
    fi
done

# 1. Stop and disable systemd service
if command -v systemctl &>/dev/null; then
    echo "Stopping and disabling systemd user service..."
    systemctl --user stop file-organizer.service 2>/dev/null || true
    systemctl --user disable file-organizer.service 2>/dev/null || true
    rm -f "${HOME}/.config/systemd/user/file-organizer.service"
    systemctl --user daemon-reload || true
    echo -e "${GREEN}✔${RESET} systemd user service removed."
fi

# 2. Remove CLI launcher
if [ -L "${HOME}/.local/bin/file-organizer" ] || [ -f "${HOME}/.local/bin/file-organizer" ]; then
    rm -f "${HOME}/.local/bin/file-organizer"
    echo -e "${GREEN}✔${RESET} Removed CLI launcher from ~/.local/bin/file-organizer."
fi

# 3. Remove application venv
APP_DIR="${HOME}/.local/share/file-organizer"
if [ -d "${APP_DIR}" ]; then
    rm -rf "${APP_DIR}"
    echo -e "${GREEN}✔${RESET} Removed application virtual environment from ${APP_DIR}."
fi

# 4. Handle configuration and logs
CONFIG_DIR="${HOME}/.config/file-organizer"
LOG_DIR="${HOME}/.local/state/file-organizer"

if [ "$PURGE" = true ]; then
    rm -rf "${CONFIG_DIR}" "${LOG_DIR}"
    echo -e "${GREEN}✔${RESET} Configuration and log files purged."
else
    echo -e "${YELLOW}ℹ Configuration (${CONFIG_DIR}) and logs (${LOG_DIR}) were preserved.${RESET}"
    echo -e "  To remove them as well, run: ${BOLD}./uninstall.sh --purge${RESET}"
fi

echo -e "\n${BOLD}${GREEN}✔ Uninstallation complete.${RESET}\n"
