#!/usr/bin/env bash
# ==============================================================================
# File Auto-Organizer Installer for Ubuntu Linux
# ==============================================================================
set -euo pipefail

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
BLUE="\033[34m"
RED="\033[31m"
RESET="\033[0m"

echo -e "${BOLD}${BLUE}=== Installing File Auto-Organizer ===${RESET}\n"

# 1. Check prerequisites
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Error: Python 3 is required but not installed.${RESET}" >&2
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "${GREEN}✔${RESET} Detected Python ${PY_VERSION}"

# Check for venv module
if ! python3 -m venv --help &>/dev/null; then
    echo -e "${RED}Error: Python venv module is missing.${RESET}" >&2
    echo -e "Please install it with: ${BOLD}sudo apt update && sudo apt install python3-venv python3-pip${RESET}" >&2
    exit 1
fi

# 2. Setup directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${HOME}/.local/share/file-organizer"
VENV_DIR="${APP_DIR}/venv"
CONFIG_DIR="${HOME}/.config/file-organizer"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
LOG_DIR="${HOME}/.local/state/file-organizer"
BIN_DIR="${HOME}/.local/bin"

mkdir -p "${APP_DIR}" "${CONFIG_DIR}" "${SYSTEMD_USER_DIR}" "${LOG_DIR}" "${BIN_DIR}"

# 3. Create or update virtual environment
echo -e "Creating virtual environment at ${VENV_DIR}..."
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/pip" install --quiet --upgrade pip setuptools wheel
echo -e "${GREEN}✔${RESET} Virtual environment ready."

# 4. Install file-organizer package
echo -e "Installing file-organizer dependencies and package..."
"${VENV_DIR}/bin/pip" install --quiet "${SCRIPT_DIR}"
echo -e "${GREEN}✔${RESET} Package installed into virtual environment."

# 5. Initialize configuration
if [ ! -f "${CONFIG_DIR}/config.yaml" ]; then
    echo -e "Copying default configuration to ${CONFIG_DIR}/config.yaml..."
    cp "${SCRIPT_DIR}/config/default_config.yaml" "${CONFIG_DIR}/config.yaml"
    echo -e "${GREEN}✔${RESET} Configuration created."
else
    echo -e "${YELLOW}ℹ${RESET} Existing configuration found at ${CONFIG_DIR}/config.yaml (preserving)."
fi

# 6. Install CLI launcher symlink
SYMLINK_PATH="${BIN_DIR}/file-organizer"
ln -sf "${VENV_DIR}/bin/file-organizer" "${SYMLINK_PATH}"
echo -e "${GREEN}✔${RESET} CLI symlink created at ${SYMLINK_PATH}"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
    echo -e "${YELLOW}Notice: ${BIN_DIR} is not in your current PATH.${RESET}"
    echo -e "You can add it by running: ${BOLD}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}"
fi

# 7. Install and enable systemd user service
echo -e "Configuring systemd user service..."
cp "${SCRIPT_DIR}/systemd/file-organizer.service" "${SYSTEMD_USER_DIR}/file-organizer.service"

if command -v systemctl &>/dev/null; then
    systemctl --user daemon-reload
    systemctl --user enable file-organizer.service
    systemctl --user restart file-organizer.service
    echo -e "${GREEN}✔${RESET} systemd user service enabled and started!"
else
    echo -e "${YELLOW}systemctl not found. Service unit installed but not started.${RESET}"
fi

# 8. Finished summary
echo -e "\n${BOLD}${GREEN}==============================================${RESET}"
echo -e "${BOLD}${GREEN}✔ Installation completed successfully!${RESET}"
echo -e "${BOLD}${GREEN}==============================================${RESET}"
echo -e "\nUseful commands:"
echo -e "  • Check status:         ${BOLD}file-organizer status${RESET} (or ${BOLD}systemctl --user status file-organizer${RESET})"
echo -e "  • One-time scan:        ${BOLD}file-organizer scan${RESET}"
echo -e "  • Dry run simulation:   ${BOLD}file-organizer scan --dry-run${RESET}"
echo -e "  • View live logs:       ${BOLD}journalctl --user -u file-organizer.service -f${RESET}"
echo -e "  • Edit configuration:   ${BOLD}nano ~/.config/file-organizer/config.yaml${RESET}"
echo -e "  • Reload after edit:    ${BOLD}file-organizer reload${RESET}"
echo ""
